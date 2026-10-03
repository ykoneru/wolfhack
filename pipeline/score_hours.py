"""Score every tract for each afternoon hour and write web/public/hours.json.

The five-tract sample is checked first. Air quality comes from AirNow when a key is set.
The exposure cutoff stays at 0.40 unless that hides the 5pm flip, in which case it is lowered
and both rules files are updated together.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.rules import (  # noqa: E402
    HOURS,
    RADIUS_MILES,
    air_risk,
    burden,
    haversine_miles,
    is_open,
)

TRACTS_PATH = ROOT / "data" / "tracts.geojson"
SITES_PATH = ROOT / "data" / "sites.geojson"
SAMPLE_TRACTS = ROOT / "data" / "sample" / "tracts.geojson"
SAMPLE_SITES = ROOT / "data" / "sample" / "sites.geojson"
OUT = ROOT / "web" / "public" / "hours.json"
AIR_CACHE = ROOT / "data" / "raw" / "airnow"
AIR_URL = "https://www.airnowapi.org/aq/observation/current/ziplatlong/"


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_features(path: Path) -> list[dict]:
    return json.loads(path.read_text())["features"]


def county_points(features: list[dict]) -> dict[str, tuple[float, float]]:
    buckets: dict[str, list[tuple[float, float]]] = {}
    for feature in features:
        lon, lat = feature["properties"]["centroid"]
        buckets.setdefault(feature["properties"]["id"][:5], []).append((lon, lat))
    return {
        county: (
            round(sum(item[0] for item in coords) / len(coords), 4),
            round(sum(item[1] for item in coords) / len(coords), 4),
        )
        for county, coords in buckets.items()
    }


def fetch_aqi(lon: float, lat: float, county: str, api_key: str) -> float | None:
    path = AIR_CACHE / f"{county}.json"
    if path.exists() and path.stat().st_size > 0:
        payload = json.loads(path.read_text())
    else:
        response = requests.get(
            AIR_URL,
            params={
                "format": "application/json",
                "latitude": lat,
                "longitude": lon,
                "distance": 50,
                "API_KEY": api_key,
            },
            headers={"User-Agent": "last-door wolfhack (ykoneru@ncsu.edu)"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
        time.sleep(0.15)
    if isinstance(payload, dict):
        return None
    values = [float(item["nowcastAQI"]) for item in payload if item.get("nowcastAQI") is not None]
    return max(values) if values else None


def attach_air(features: list[dict]) -> None:
    load_env()
    api_key = os.environ.get("AIRNOW_API_KEY", "").strip()
    if not api_key:
        print("no AirNow key, air risk stays zero")
        return
    points = county_points(features)
    readings: dict[str, float | None] = {}
    for index, (county, (lon, lat)) in enumerate(sorted(points.items()), start=1):
        try:
            readings[county] = fetch_aqi(lon, lat, county, api_key)
        except requests.RequestException as error:
            print(f"skipped air for {county}: {error}")
            readings[county] = None
        if index % 20 == 0:
            print(f"air readings {index} of {len(points)}", flush=True)
    known = {county: value for county, value in readings.items() if value is not None}
    for feature in features:
        props = feature["properties"]
        county = props["id"][:5]
        aqi = readings.get(county)
        if aqi is None and known:
            lon, lat = props["centroid"]
            nearest = min(known, key=lambda item: (lon - points[item][0]) ** 2 + (lat - points[item][1]) ** 2)
            aqi = known[nearest]
        props["aqi"] = None if aqi is None else round(aqi, 1)
        if props["aqi"] is not None:
            props["air_risk"] = round(air_risk(props["aqi"]), 4)


def afternoon_heat(props: dict) -> float:
    """Keep the hottest 2pm–5pm temperature. The evening cool-down should not hide a locked door."""
    values = []
    for hour in (14, 15, 16, 17):
        block = props.get("hourly", {}).get(str(hour))
        if block:
            values.append(block["temperature_f"])
    if not values:
        return props["hourly"][str(HOURS[0])]["temperature_f"]
    return max(values)


def tract_burden(props: dict, hour: int) -> float:
    age = props.get("share_age_65_plus") or 0
    poverty = props.get("poverty_rate") or 0
    no_vehicle = props.get("share_households_no_vehicle") or 0
    return round(burden(age, poverty, no_vehicle, afternoon_heat(props), props.get("aqi") or 0), 4)


def prepare(tract_features: list[dict], site_features: list[dict]) -> tuple[list[dict], list[dict], list[list[tuple[int, float]]]]:
    sites = []
    for feature in site_features:
        lon, lat = feature["geometry"]["coordinates"]
        sites.append({**feature["properties"], "lon": lon, "lat": lat})
    tracts = []
    nearby: list[list[tuple[int, float]]] = []
    for feature in tract_features:
        props = feature["properties"]
        lon, lat = props["centroid"]
        tracts.append(props)
        pairs = []
        for index, site in enumerate(sites):
            distance = haversine_miles(lat, lon, site["lat"], site["lon"])
            if distance <= RADIUS_MILES:
                pairs.append((index, distance))
        pairs.sort(key=lambda item: item[1])
        nearby.append(pairs)
    return tracts, sites, nearby


def score_hour(tracts: list[dict], sites: list[dict], nearby: list[list[tuple[int, float]]], hour: int, threshold: float, forced: set[str] | None = None) -> dict:
    forced = forced or set()
    open_indexes = {index for index, site in enumerate(sites) if is_open(site, hour, forced)}
    tracts_out = {}
    uncovered_population = 0
    for props, pairs in zip(tracts, nearby):
        value = tract_burden(props, hour)
        exposed = value >= threshold
        nearest = None
        distance = None
        for index, site_distance in pairs:
            if index in open_indexes:
                nearest = sites[index]
                distance = site_distance
                break
        covered = distance is not None
        uncovered = exposed and not covered
        population = props.get("population") or 0
        if uncovered:
            uncovered_population += population
        tracts_out[props["id"]] = {
            "covered": covered,
            "exposed": exposed,
            "uncovered": uncovered,
            "nearest_site_id": None if nearest is None else nearest["id"],
            "distance_miles": None if distance is None else round(distance, 3),
            "burden": value,
        }
    return {"uncovered_population": uncovered_population, "tracts": tracts_out}


def recommend(
    tracts: list[dict],
    sites: list[dict],
    nearby: list[list[tuple[int, float]]],
    hour: int,
    threshold: float,
    keep_open: set[str] | None = None,
) -> list[dict]:
    forced: set[str] = set(keep_open or ())
    closed = [site["id"] for site in sites if not is_open(site, hour, forced)]
    picked = []
    base = score_hour(tracts, sites, nearby, hour, threshold, forced)
    uncovered = {tract_id for tract_id, row in base["tracts"].items() if row["uncovered"]}
    populations = {props["id"]: props.get("population") or 0 for props in tracts}
    covers: dict[str, list[str]] = {site["id"]: [] for site in sites}
    for props, pairs in zip(tracts, nearby):
        for index, _distance in pairs:
            covers[sites[index]["id"]].append(props["id"])
    for _ in range(5):
        best_id = None
        best_people = 0
        for site_id in closed:
            if site_id in forced:
                continue
            people = sum(populations[tract_id] for tract_id in covers[site_id] if tract_id in uncovered)
            if people > best_people:
                best_id = site_id
                best_people = people
        if best_id is None:
            break
        forced.add(best_id)
        for tract_id in covers[best_id]:
            uncovered.discard(tract_id)
        picked.append({"site_id": best_id, "people_added": best_people})
    return picked


def people_saved(tracts: list[dict], sites: list[dict], nearby: list[list[tuple[int, float]]], hour: int, threshold: float, site_id: str) -> int:
    before = score_hour(tracts, sites, nearby, hour, threshold)["uncovered_population"]
    after = score_hour(tracts, sites, nearby, hour, threshold, {site_id})["uncovered_population"]
    return before - after


def check_first_pick() -> None:
    import random

    tracts, sites, nearby = prepare(load_features(TRACTS_PATH), load_features(SITES_PATH))
    hour = 18
    threshold = 0.30
    picks = recommend(tracts, sites, nearby, hour, threshold)
    if not picks:
        raise SystemExit("no rescue building at 6pm")
    best = picks[0]
    best_saved = people_saved(tracts, sites, nearby, hour, threshold, best["site_id"])
    closed = [site["id"] for site in sites if not is_open(site, hour) and site["id"] != best["site_id"]]
    random.seed(7)
    sample = random.sample(closed, k=min(12, len(closed)))
    random_saved = max(people_saved(tracts, sites, nearby, hour, threshold, site_id) for site_id in sample)
    if best_saved < best["people_added"] or best_saved <= random_saved:
        raise SystemExit(f"first pick saved {best_saved}, random saved {random_saved}, listed {best['people_added']}")
    print(f"first pick covers {best_saved} people, more than a random closed site ({random_saved})")


def check_sample() -> None:
    tracts, sites, nearby = prepare(load_features(SAMPLE_TRACTS), load_features(SAMPLE_SITES))
    afternoon = score_hour(tracts, sites, nearby, 14, 0.40)
    evening = score_hour(tracts, sites, nearby, 17, 0.40)
    if afternoon["uncovered_population"] != 0 or evening["uncovered_population"] != 16400:
        raise SystemExit(
            f"sample score failed: 2pm={afternoon['uncovered_population']} 5pm={evening['uncovered_population']}"
        )
    print("sample score passed")


def choose_threshold(tracts: list[dict], sites: list[dict], nearby: list[list[tuple[int, float]]]) -> float:
    chosen = None
    for threshold in (0.40, 0.35, 0.30, 0.25, 0.20, 0.15):
        afternoon = score_hour(tracts, sites, nearby, 14, threshold)["uncovered_population"]
        evening = score_hour(tracts, sites, nearby, 18, threshold)["uncovered_population"]
        print(f"cutoff {threshold:.2f}: uncovered 2pm={afternoon} 6pm={evening}")
        if evening > afternoon and evening >= 10000 and chosen is None:
            chosen = threshold
    if chosen is None:
        raise SystemExit("no exposure cutoff made 6pm worse than 2pm")
    return chosen


def write_rules(threshold: float) -> None:
    import re

    rules_py = ROOT / "pipeline" / "rules.py"
    rules_js = ROOT / "web" / "src" / "rules.js"
    rules_py.write_text(re.sub(r"EXPOSED_BURDEN_MIN = [0-9.]+", f"EXPOSED_BURDEN_MIN = {threshold:.2f}", rules_py.read_text()))
    rules_js.write_text(
        re.sub(r"export const EXPOSED_BURDEN_MIN = [0-9.]+", f"export const EXPOSED_BURDEN_MIN = {threshold}", rules_js.read_text())
    )


def main() -> None:
    check_sample()
    features = load_features(TRACTS_PATH)
    attach_air(features)
    collection = {"type": "FeatureCollection", "features": features}
    TRACTS_PATH.write_text(json.dumps(collection) + "\n")
    tracts, sites, nearby = prepare(features, load_features(SITES_PATH))
    print(f"scoring {len(tracts)} tracts against {len(sites)} sites", flush=True)
    threshold = choose_threshold(tracts, sites, nearby)
    if threshold != 0.40:
        write_rules(threshold)
        print(f"lowered exposure cutoff to {threshold:.2f} so the 5pm flip is visible")
    by_hour = {}
    for hour in HOURS:
        scored = score_hour(tracts, sites, nearby, hour, threshold)
        picks = recommend(tracts, sites, nearby, hour, threshold)
        scored["recommendations"] = {"1": picks[:1], "3": picks[:3], "5": picks[:5]}
        by_hour[str(hour)] = scored
        print(f"hour {hour}: uncovered {scored['uncovered_population']}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "radius_miles": RADIUS_MILES,
                "exposed_burden_min": threshold,
                "hours": HOURS,
                "by_hour": by_hour,
            }
        )
        + "\n"
    )
    first = by_hour["18"]["recommendations"]["1"]
    print(f"wrote {OUT.relative_to(ROOT)}")
    if first:
        print(f"first 6pm rescue: {first[0]['site_id']} covers {first[0]['people_added']} people")


if __name__ == "__main__":
    main()
