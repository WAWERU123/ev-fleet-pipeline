import requests

def get_ambient_temp(lat, lon):
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": lat, "longitude": lon, "current": "temperature_2m"},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()["current"]["temperature_2m"]

print(get_ambient_temp(-1.3, 36.85))