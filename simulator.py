import random
import sys
import time
import uuid
from datetime import datetime, timezone
import requests

URL = "http://127.0.0.1:8000/ingest"

buses = {
    "BUS-01": {"soc": 90.0, "temp": 28.0, "odo": 12000.0, "lat": -1.2921, "lon": 36.8219},
    "BUS-02": {"soc": 75.0, "temp": 30.0, "odo": 8500.0,  "lat": -1.2833, "lon": 36.8167},
    "BUS-03": {"soc": 60.0, "temp": 29.0, "odo": 20300.0, "lat": -1.3000, "lon": 36.8500},
}

def next_reading(bus_id):
    s = buses[bus_id]
    s["soc"] = max(0, s["soc"] - random.uniform(0.05, 0.2))
    s["temp"] += random.uniform(-0.5, 0.5)
    s["odo"] += random.uniform(0.3, 0.8)
    s["lat"] += random.uniform(-0.0005, 0.0005)
    s["lon"] += random.uniform(-0.0005, 0.0005)
    return {
        "event_id": str(uuid.uuid4()),
        "bus_id": bus_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "soc": round(s["soc"], 2),
        "battery_temp_c": round(s["temp"], 2),
        "odometer_km": round(s["odo"], 2),
        "lat": round(s["lat"], 5),
        "lon": round(s["lon"], 5),
    }

for bus_id in buses:
    reading = next_reading(bus_id)
    response = requests.post(URL, json=reading)
    print(bus_id, response.status_code, response.json()["status"])


fault = sys.argv[1] if len(sys.argv) > 1 else None
round_no = 0

while True:
    round_no += 1
    for bus_id in buses:
        reading = next_reading(bus_id)
        if fault == "temp_spike" and bus_id == "BUS-02" and round_no == 3:
            reading["battery_temp_c"] = 58.0
        response = requests.post(URL, json=reading)
        print(bus_id, response.status_code, response.json()["status"])
    print("--- round complete ---")
    time.sleep(10)