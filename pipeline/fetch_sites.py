"""Download cooling sites for North Carolina.

Libraries and community centers come from the Overpass API.
Hospitals come from NC OneMap and stay open overnight.
Raw responses stay in data/raw, which is gitignored.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.rules import haversine_miles  # noqa: E402

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "sites.geojson"
SOUTH, WEST, NORTH, EAST = 33.75, -84.5, 36.62, -75.4
DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
SCENARIO_DAY = "Fr"
DEFAULT_CLOSE_HOUR = 17
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
HOSPITAL_URL = (
    "https://services.nconemap.gov/secure/rest/services/NC1Map_Health/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson"
)
TIME_RANGE = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")
DAY_RANGE = re.compile(r"(Mo|Tu|We|Th|Fr|Sa|Su)\s*-\s*(Mo|Tu|We|Th|Fr|Sa|Su)")
DAY_TOKEN = re.compile(r"Mo|Tu|We|Th|Fr|Sa|Su")


def end_hour(rule: str) -> int | None:
    matches = TIME_RANGE.findall(rule)
    if not matches:
        return None
    hour = int(matches[-1][2])
    minute = int(matches[-1][3])
    if minute > 0:
        hour += 1
    return min(hour, 24)


def days_in(rule: str) -> set[str] | None:
    head = re.split(r"\d", rule, maxsplit=1)[0]
    if not DAY_TOKEN.search(head):
        return None
    found: set[str] = set()
    for start, stop in DAY_RANGE.findall(head):
        start_index = DAYS.index(start)
        stop_index = DAYS.index(stop)
        if start_index <= stop_index:
            found.update(DAYS[start_index : stop_index + 1])
        else:
            found.update(DAYS[start_index:])
            found.update(DAYS[: stop_index + 1])
    leftover = DAY_RANGE.sub(" ", head)
    found.update(DAY_TOKEN.findall(leftover))
    return found


def parse_close_hour(opening_hours: str | None) -> tuple[int | None, str]:
    if not opening_hours or not opening_hours.strip():
        return DEFAULT_CLOSE_HOUR, "default"
    text = opening_hours.strip()
    if "24/7" in text.replace(" ", ""):
        return None, "osm"
    friday_ends = []
    saw_day_rule = False
    for rule in [part.strip() for part in text.split(";") if part.strip()]:
        if rule.lower() == "closed":
            continue
        ending = end_hour(rule)
        if ending is None:
            continue
        days = days_in(rule)
        if days is None:
            friday_ends.append(ending)
            continue
        saw_day_rule = True
        if SCENARIO_DAY in days:
            friday_ends.append(ending)
    if friday_ends:
        return max(friday_ends), "osm"
    if saw_day_rule:
        return 0, "osm"
    return DEFAULT_CLOSE_HOUR, "default"


def check_parser() -> None:
    cases = {
        "Mo-Fr 09:00-17:00": (17, "osm"),
        "24/7": (None, "osm"),
        None: (17, "default"),
        "Mo-Fr 09:00-20:00; Sa 10:00-17:00": (20, "osm"),
        "Sa-Su 10:00-17:00": (0, "osm"),
        "Mo-Th 10:00-20:00": (0, "osm"),
    }
    for hours, expected in cases.items():
        got = parse_close_hour(hours)
        if got != expected:
            raise SystemExit(f"hours parser failed for {hours!r}: {got} != {expected}")


def overpass_queries() -> list[str]:
    bbox = f"({SOUTH},{WEST},{NORTH},{EAST})"
    filters = [
        f'node["amenity"="library"]{bbox};',
        f'way["amenity"="library"]{bbox};',
        f'node["amenity"="community_centre"]{bbox};',
        f'way["amenity"="community_centre"]{bbox};',
        f'node["social_facility"="shelter"]{bbox};',
        f'way["social_facility"="shelter"]{bbox};',
        f'node["social_facility"="community_centre"]{bbox};',
        f'way["social_facility"="community_centre"]{bbox};',
    ]
    return [f"[out:json][timeout:60];\n{item}\nout center;" for item in filters]


def fetch_overpass() -> dict:
    cache = RAW / "overpass_sites.json"
    if cache.exists() and cache.stat().st_size > 0:
        print(f"using cached {cache.name}")
        return json.loads(cache.read_text())
    headers = {"User-Agent": "last-door wolfhack (ykoneru@ncsu.edu)", "Accept": "*/*"}
    elements = []
    seen = set()
    for query in overpass_queries():
        payload = None
        last_error = None
        for url in OVERPASS_URLS:
            try:
                response = requests.post(url, data={"data": query}, headers=headers, timeout=50)
            except requests.RequestException as error:
                last_error = str(error)
                continue
            if response.status_code != 200:
                last_error = f"{url} returned {response.status_code}: {response.text[:120]}"
                continue
            payload = response.json()
            break
        if payload is None:
            print(f"skipped a query: {last_error}")
            continue
        for element in payload.get("elements", []):
            key = (element.get("type"), element.get("id"))
            if key in seen:
                continue
            seen.add(key)
            elements.append(element)
        print(f"overpass elements so far: {len(elements)}", flush=True)
    result = {"elements": elements}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result))
    return result


def fetch_hospitals() -> dict:
    cache = RAW / "nconemap_hospitals.geojson"
    if cache.exists() and cache.stat().st_size > 0:
        print(f"using cached {cache.name}")
        return json.loads(cache.read_text())
    print("requesting NC OneMap hospitals")
    response = requests.get(HOSPITAL_URL, timeout=120)
    response.raise_for_status()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(response.content)
    return response.json()


def site_feature(site_id: str, name: str, site_type: str, lon: float, lat: float, close_hour, hours_source: str) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        "properties": {
            "id": site_id,
            "name": name,
            "type": site_type,
            "close_hour": close_hour,
            "hours_source": hours_source,
        },
    }


def osm_features(payload: dict) -> list[dict]:
    features = []
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        lat = element.get("lat", (element.get("center") or {}).get("lat"))
        lon = element.get("lon", (element.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        site_type = tags.get("amenity") or tags.get("social_facility") or "community_centre"
        if site_type not in {"library", "community_centre", "shelter"}:
            continue
        close_hour, hours_source = parse_close_hour(tags.get("opening_hours"))
        name = tags.get("name") or f"Unnamed {site_type.replace('_', ' ')}"
        features.append(
            site_feature(
                f"osm-{element['type']}-{element['id']}",
                name,
                site_type,
                float(lon),
                float(lat),
                close_hour,
                hours_source,
            )
        )
    return features


def hospital_features(payload: dict) -> list[dict]:
    features = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates")
        if geometry.get("type") != "Point" or not coordinates:
            continue
        props = feature.get("properties") or {}
        name = props.get("altfacname") or props.get("name") or "Hospital"
        site_id = props.get("licno") or props.get("OBJECTID") or props.get("objectid") or len(features)
        features.append(site_feature(f"nconemap-{site_id}", str(name), "hospital", coordinates[0], coordinates[1], None, "nconemap"))
    return features


def keep_site(feature: dict) -> bool:
    name = feature["properties"]["name"].strip().lower()
    if "little free" in name or name in {"entrance/exit", "unnamed library"}:
        return False
    return True


def inside_north_carolina(features: list[dict]) -> list[dict]:
    import geopandas as gpd
    from shapely import contains_xy
    from shapely.ops import unary_union

    tracts = gpd.read_file(ROOT / "data" / "tracts.geojson")
    state = unary_union(tracts.geometry)
    kept = []
    for feature in features:
        lon, lat = feature["geometry"]["coordinates"]
        if contains_xy(state, lon, lat):
            kept.append(feature)
    return kept


def dedupe(features: list[dict]) -> list[dict]:
    kept = []
    for feature in features:
        lon, lat = feature["geometry"]["coordinates"]
        name = feature["properties"]["name"].strip().lower()
        duplicate = False
        for other in kept:
            other_lon, other_lat = other["geometry"]["coordinates"]
            same_name = other["properties"]["name"].strip().lower() == name
            if same_name and haversine_miles(lat, lon, other_lat, other_lon) < 0.15:
                duplicate = True
                break
        if not duplicate:
            kept.append(feature)
    return kept


def main() -> None:
    check_parser()
    elements = fetch_overpass()
    library_ways = RAW / "library_ways.json"
    if library_ways.exists():
        elements = {"elements": elements.get("elements", []) + json.loads(library_ways.read_text()).get("elements", [])}
    features = osm_features(elements) + hospital_features(fetch_hospitals())
    features = [feature for feature in features if keep_site(feature)]
    features = inside_north_carolina(features)
    features = dedupe(features)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2) + "\n")

    counts: dict[str, int] = {}
    sources: dict[str, int] = {}
    for feature in features:
        props = feature["properties"]
        counts[props["type"]] = counts.get(props["type"], 0) + 1
        sources[props["hours_source"]] = sources.get(props["hours_source"], 0) + 1
    closed_library = next(
        (
            feature["properties"]
            for feature in features
            if feature["properties"]["type"] == "library" and feature["properties"]["close_hour"] == 17
        ),
        None,
    )
    hospital = next((feature["properties"] for feature in features if feature["properties"]["type"] == "hospital"), None)
    print(f"wrote {len(features)} sites to {OUT.relative_to(ROOT)}")
    print(f"types {counts}")
    print(f"hour sources {sources}")
    if closed_library is None or hospital is None or hospital["close_hour"] is not None:
        raise SystemExit("expected a library that closes at 5pm and a hospital that stays open")
    print(f"closes at 5pm: {closed_library['name']} ({closed_library['hours_source']})")
    print(f"stays open: {hospital['name']}")


if __name__ == "__main__":
    main()
