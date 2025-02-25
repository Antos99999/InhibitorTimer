import requests
import time
from flask import Flask, render_template, jsonify
import threading
import urllib3

# Wyłączanie ostrzeżeń HTTPS (bo korzystamy z lokalnego API bez certyfikatu)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Czas respawnu inhibitora (5 minut = 300 sekund)
RESPAWN_TIME = 300

# Mapa inhibitorów
inhibitors = {
    "Red mid": "Inhib_T200_L1_P1_1931666598",
    "Red bot": "Inhib_T200_L0_P1_2116220407",
    "Red top": "Inhib_T200_L2_P1_2351107073",
    "Blue mid": "Inhib_T100_L1_P1_2786523670",
    "Blue bot": "Inhib_T100_L0_P1_2971077479",
    "Blue top": "Inhib_T100_L2_P1_2669080337"
}

# Przechowuje czasy końca timerów { inhibitor_id: end_time }
destroy_times = {}

# Zapamiętane EventID (żeby nie obsługiwać duplikatów)
processed_events = set()

# Lock do synchronizacji wątków
lock = threading.Lock()


def start_timer(inhibitor_id):
    with lock:
        end_time = time.time() + RESPAWN_TIME
        destroy_times[inhibitor_id] = end_time

    while time.time() < end_time:
        time.sleep(1)

    with lock:
        if destroy_times.get(inhibitor_id) == end_time:  # Sprawdzenie czy to nadal aktualny timer
            destroy_times.pop(inhibitor_id, None)

    print(f"Inhibitor {inhibitor_id} zrespawnował się!")


# Pobieranie eventów co sekundę
def poll_events():
    while True:
        try:
            response = requests.get("https://127.0.0.1:2999/liveclientdata/eventdata", verify=False)
            response.raise_for_status()
            data = response.json()

            for event in data.get('Events', []):
                if event['EventName'] == 'InhibKilled':
                    event_id = event['EventID']
                    inhib_id = event['InhibKilled']

                    if inhib_id in inhibitors.values() and event_id not in processed_events:
                        processed_events.add(event_id)  # Oznaczamy event jako obsłużony
                        print(f"Zniszczono inhibitor: {inhib_id}, Czas: {event['EventTime']:.2f}s")
                        threading.Thread(target=start_timer, args=(inhib_id,), daemon=True).start()

        except requests.exceptions.RequestException as e:
            print(f"Błąd w pobieraniu danych: {e}")

        time.sleep(1)  # Czekamy sekundę przed kolejnym sprawdzeniem


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/data')
def get_data():
    with lock:
        current_time = time.time()
        time_lefts = {
            inhib_name: max(0, int(destroy_times.get(inhib_id, 0) - current_time))
            for inhib_name, inhib_id in inhibitors.items()
        }

    formatted_times = {
        name: f"{time // 60}:{str(time % 60).zfill(2)}" if time > 0 else "0:00"
        for name, time in time_lefts.items()
    }

    return jsonify(formatted_times)


if __name__ == '__main__':
    threading.Thread(target=poll_events, daemon=True).start()  # Startujemy pętlę pobierania eventów
    app.run(debug=True, port=5000, use_reloader=False)
