"""Attach the National Weather Service hourly forecast to each NC tract.

One forecast is downloaded per county, then copied to every tract in that county.
Air quality is left empty until AIRNOW_API_KEY is set. Raw responses stay in data/raw.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.rules import HOURS, heat_risk  # noqa: E402

TRACTS_PATH = ROOT / "data" / "tracts.geojson"
CACHE = ROOT / "data" / "raw" / "nws"
EASTERN = ZoneInfo("America/New_York")
HEADERS = {
    "User-Agent": "last-door wolfhack (ykoneru@ncsu.edu)",
    "Accept": "application/geo+json",
}


def county_points(features: list[dict]) -> dict[str, tuple[float, float]]:
    buckets: dict[str, list[tuple[float, float]]] = {}
    for feature in features:
        props = feature["properties"]
        county = props["id"][:5]
        lon, lat = props["centroid"]
        buckets.setdefault(county, []).append((lon, lat))
    points = {}
    for county, coords in buckets.items():
        lon = sum(item[0] for item in coords) / len(coords)
        lat = sum(item[1] for item in coords) / len(coords)
        points[county] = (round(lon, 4), round(lat, 4))
    return points


def cached_get(url: str, path: Path) -> dict:
    if path.exists() and path.stat().st_size > 0:
        return json.loads(path.read_text())
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    time.sleep(0.2)
    return response.json()


def hourly_temperatures(lon: float, lat: float, county: str) -> dict[str, dict]:
    points = cached_get(
        f"https://api.weather.gov/points/{lat},{lon}",
        CACHE / f"{county}-points.json",
    )
    hourly_url = points["properties"]["forecastHourly"]
    forecast = cached_get(hourly_url, CACHE / f"{county}-hourly.json")
    temperatures: dict[str, dict] = {}
    for period in forecast["properties"]["periods"]:
        if period.get("temperatureUnit") != "F":
            continue
        local = datetime.fromisoformat(period["startTime"]).astimezone(EASTERN)
        if local.hour not in HOURS:
            continue
        hour = str(local.hour)
        if hour in temperatures:
            continue
        temp = float(period["temperature"])
        temperatures[hour] = {
            "temperature_f": temp,
            "heat_risk": round(heat_risk(temp), 4),
        }
    return temperatures


def fetch_counties(points: dict[str, tuple[float, float]]) -> dict[str, dict[str, dict]]:
    forecasts = {}
    for index, (county, (lon, lat)) in enumerate(sorted(points.items()), start=1):
        try:
            forecasts[county] = hourly_temperatures(lon, lat, county)
        except requests.RequestException as error:
            print(f"skipped {county}: {error}")
            continue
        if index % 20 == 0:
            print(f"fetched {index} of {len(points)} counties", flush=True)
    return forecasts


def nearest_forecast(lon: float, lat: float, points: dict[str, tuple[float, float]], forecasts: dict[str, dict]) -> dict:
    best = None
    best_distance = None
    for county, hourly in forecasts.items():
        if len(hourly) < len(HOURS):
            continue
        other_lon, other_lat = points[county]
        distance = (lon - other_lon) ** 2 + (lat - other_lat) ** 2
        if best_distance is None or distance < best_distance:
            best = hourly
            best_distance = distance
    return best or {}


def main() -> None:
    tracts = json.loads(TRACTS_PATH.read_text())
    points = county_points(tracts["features"])
    print(f"fetching hourly forecasts for {len(points)} counties", flush=True)
    forecasts = fetch_counties(points)
    ready = [county for county, hourly in forecasts.items() if all(str(hour) in hourly for hour in HOURS)]
    print(f"{len(ready)} counties have 2pm through 8pm")

    for feature in tracts["features"]:
        props = feature["properties"]
        county = props["id"][:5]
        hourly = forecasts.get(county) or {}
        if not all(str(hour) in hourly for hour in HOURS):
            lon, lat = props["centroid"]
            hourly = nearest_forecast(lon, lat, points, forecasts)
        props["hourly"] = {str(hour): hourly[str(hour)] for hour in HOURS if str(hour) in hourly}
        props["aqi"] = None

    TRACTS_PATH.write_text(json.dumps(tracts) + "\n")
    wake = next(
        feature["properties"]
        for feature in tracts["features"]
        if feature["properties"]["id"].startswith("37183") and feature["properties"].get("hourly")
    )
    print(f"example {wake['id']} {wake['name']}")
    for hour in (16, 17, 18):
        block = wake["hourly"].get(str(hour))
        if block is None:
            raise SystemExit(f"missing {hour}:00 temperature")
        print(f"  {hour}:00 {block['temperature_f']} F")
    print("aqi is empty until an AirNow key is added")


if __name__ == "__main__":
    main()
