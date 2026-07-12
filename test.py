import requests

URL = (
    "https://aviationweather.gov/api/data/metar"
    "?ids=KMIA"
    "&format=json"
    "&hours=24"
)

headers = {
    "User-Agent": "my-weather-app/1.0 (your_email@example.com)"
}

response = requests.get(URL, headers=headers)
response.raise_for_status()

metars = response.json()

temps = [
    m["temp"]
    for m in metars
    if m.get("temp") is not None
]

if temps:
    print(f"Today's highest observed temperature at KMIA: {max(temps)}°C")
else:
    print("No temperature observations found.")