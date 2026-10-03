"""Score a typical weekday for every Wake County tract and write the map files."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.flowmap import (  # noqa: E402
    BASE_WEIGHT,
    COMMUTE_MAX,
    DEFAULT_HOURS,
    DESTINATION_MAX,
    HOURS,
    POPULATION_MAX,
    ROAD_MAX,
    category_for,
    hour_multiplier,
    p95,
    weather_multiplier,
)

TRACTS_PATH = ROOT / "data" / "tracts.geojson"
COMMUTE_PATH = ROOT / "data" / "raw" / "commute.json"
PLACES_PATH = ROOT / "data" / "raw" / "flowmap-places.json"
ROADS_PATH = ROOT / "data" / "raw" / "flowmap-roads.json"
WAKE = "37183"

# ACS bins assigned to clock hours. The 4pm–midnight bin is one published number;
# it is placed on 4pm, 5pm, and 6pm and is not treated as a measured 7–10pm commute.
BIN_HOURS = {
    "B08302008": [8],
    "B08302009": [8],
    "B08302010": [8],
    "B08302011": [9],
    "B08302012": [10],
    "B08302013": [11],
    "B08302014": [12, 13, 14, 15],
    "B08302015": [16, 17, 18],
}


def category_of(tags: dict) -> str | None:
    amenity = tags.get("amenity")
    shop = tags.get("shop")
    leisure = tags.get("leisure")
    if amenity == "cafe":
        return "cafe"
    if amenity == "restaurant":
        return "restaurant"
    if amenity == "fast_food":
        return "fast_food"
    if amenity in {"bar", "pub", "nightclub"}:
        return "bar"
    if amenity == "library":
        return "library"
    if amenity == "hospital":
        return "hospital"
    if amenity in {"university", "college"}:
        return "university"
    if amenity == "school":
        return "school"
    if amenity in {"theatre", "cinema"}:
        return "entertainment"
    if amenity == "marketplace" or shop in {"mall", "department_store"}:
        return "shopping"
    if shop in {"supermarket", "convenience"}:
        return "grocery"
    if leisure in {"fitness_centre", "sports_centre"}:
        return "gym"
    if leisure == "park":
        return "park"
    return None


def parse_hours(raw: str | None, category: str) -> dict:
    default_open, default_close = DEFAULT_HOURS[category]
    if not raw:
        return {"open": default_open, "close": default_close, "source": "default"}
    text = raw.lower()
    if "24/7" in text or "24 hours" in text:
        return {"open": 0, "close": 24, "source": "osm"}
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?", text)
    if not match:
        return {"open": default_open, "close": default_close, "source": "default"}
    open_hour = int(match.group(1))
    close_hour = int(match.group(3))
    close_minutes = int(match.group(4) or 0)
    if close_minutes:
        close_hour += 1
    if close_hour <= open_hour:
        close_hour += 12 if close_hour <= 12 else 0
    close_hour = min(max(close_hour, open_hour + 1), 24)
    return {"open": open_hour, "close": close_hour, "source": "osm"}


def element_point(element: dict) -> tuple[float, float] | None:
    if element["type"] == "node" and element.get("lat") is not None:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if center.get("lat") is None:
        return None
    return float(center["lat"]), float(center["lon"])


def load_commute() -> dict[str, dict[int, float]]:
    payload = json.loads(COMMUTE_PATH.read_text())
    by_tract = {}
    for geoid, tables in payload["data"].items():
        tract_id = geoid.removeprefix("14000US")
        estimate = tables["B08302"]["estimate"]
        total = float(estimate.get("B08302001") or 0)
        shares = {hour: 0.0 for hour in HOURS}
        profile = {"workers": int(total), "morning_share": 0.0, "evening_bin_share": 0.0}
        if total > 0:
            morning = sum(float(estimate.get(code) or 0) for code in ("B08302007", "B08302008", "B08302009", "B08302010"))
            profile["morning_share"] = round(morning / total, 4)
            profile["evening_bin_share"] = round(float(estimate.get("B08302015") or 0) / total, 4)
            for code, hours in BIN_HOURS.items():
                portion = float(estimate.get(code) or 0) / len(hours) / total
                for hour in hours:
                    shares[hour] += portion
        by_tract[tract_id] = {"shares": shares, "profile": profile}
    return by_tract


def load_points(path: Path, places: bool) -> list[dict]:
    elements = json.loads(path.read_text()).get("elements", [])
    rows = []
    seen = set()
    for element in elements:
        point = element_point(element)
        if point is None:
            continue
        lat, lon = point
        key = (element["type"], element["id"])
        if key in seen:
            continue
        seen.add(key)
        if places:
            tags = element.get("tags") or {}
            category = category_of(tags)
            if category is None:
                continue
            hours = parse_hours(tags.get("opening_hours"), category)
            name = tags.get("name")
            named = isinstance(name, str) and bool(name.strip())
            rows.append(
                {
                    "id": f"osm-{element['type']}-{element['id']}",
                    "name": name.strip() if named else f"{category.replace('_', ' ').title()} place",
                    "named": named,
                    "category": category,
                    "lat": round(lat, 5),
                    "lon": round(lon, 5),
                    "open": hours["open"],
                    "close": hours["close"],
                    "hours_source": hours["source"],
                }
            )
        else:
            rows.append({"id": f"osm-{element['type']}-{element['id']}", "lat": lat, "lon": lon})
    return rows


def assign_tracts(rows: list[dict], tracts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    points = gpd.GeoDataFrame(rows, geometry=[Point(row["lon"], row["lat"]) for row in rows], crs="EPSG:4326")
    joined = gpd.sjoin(
        points, tracts[["id", "geometry"]], how="inner", predicate="within", lsuffix="place", rsuffix="tract"
    )
    id_column = "id_place" if "id_place" in joined.columns else "id"
    return joined.drop_duplicates(id_column)


def main() -> None:
    tracts = gpd.read_file(TRACTS_PATH)
    tracts = tracts[tracts["id"].astype(str).str.startswith(WAKE)].copy()
    tracts["id"] = tracts["id"].astype(str)
    tracts = tracts.reset_index(drop=True)
    metric = tracts.to_crs(32617)
    tracts["area_km2"] = metric.geometry.area / 1_000_000
    tracts["density"] = tracts["population"].fillna(0) / tracts["area_km2"].clip(lower=0.01)
    commute = load_commute()
    places = assign_tracts(load_points(PLACES_PATH, True), tracts)
    roads = assign_tracts(load_points(ROADS_PATH, False), tracts)
    tract_column = "id_tract" if "id_tract" in places.columns else "id_right"
    places_by_tract = defaultdict(list)
    for _, record in places.iterrows():
        places_by_tract[str(record[tract_column])].append(record)
    road_column = "id_tract" if "id_tract" in roads.columns else "id_right"
    road_counts = roads.groupby(road_column).size().to_dict()
    density_scale = p95([float(value) for value in tracts["density"]])
    road_scale = p95([float(value) for value in road_counts.values()]) or 1.0
    commute_peaks = []
    for tract_id, payload in commute.items():
        if tract_id in set(tracts["id"]):
            commute_peaks.append(max(payload["shares"].values()))
    commute_scale = p95(commute_peaks) or 1.0

    raw_by_hour = {hour: {} for hour in HOURS}
    base_by_hour = {hour: {} for hour in HOURS}
    for tract_id, items in places_by_tract.items():
        for hour in HOURS:
            indoor = 0.0
            outdoor = 0.0
            outdoor_base = 0.0
            tract_row = tracts.loc[tracts["id"] == tract_id]
            temperature = None
            aqi = None
            if not tract_row.empty:
                hourly = tract_row.iloc[0]["hourly"]
                if isinstance(hourly, str):
                    hourly = json.loads(hourly)
                block = hourly.get(str(hour)) if isinstance(hourly, dict) else None
                if isinstance(block, dict):
                    temperature = block.get("temperature_f")
                aqi = tract_row.iloc[0]["aqi"]
                if aqi != aqi:
                    aqi = None
            outdoor_multiplier, _measured = weather_multiplier(None if temperature is None else float(temperature), None if aqi is None else float(aqi))
            for place in items:
                if not (place["open"] <= hour < place["close"]):
                    continue
                weight = BASE_WEIGHT[place["category"]] * hour_multiplier(place["category"], hour)
                if place["category"] == "park":
                    outdoor_base += weight
                    outdoor += weight * outdoor_multiplier
                else:
                    indoor += weight
            raw_by_hour[hour][tract_id] = indoor + outdoor
            base_by_hour[hour][tract_id] = indoor + outdoor_base
    destination_scale = p95(list(raw_by_hour[17].values())) or 1.0

    activity = {}
    features = []
    for _, tract in tracts.iterrows():
        tract_id = str(tract["id"])
        profile = commute.get(tract_id, {"shares": {hour: 0.0 for hour in HOURS}, "profile": {"workers": 0, "morning_share": 0.0, "evening_bin_share": 0.0}})
        population_points = round(min(POPULATION_MAX, POPULATION_MAX * float(tract["density"]) / density_scale), 2)
        road_points = round(min(ROAD_MAX, ROAD_MAX * float(road_counts.get(tract_id, 0)) / road_scale), 2)
        hours = {}
        for hour in HOURS:
            commute_points = round(min(COMMUTE_MAX, COMMUTE_MAX * profile["shares"][hour] / commute_scale), 2)
            destination_points = round(min(DESTINATION_MAX, DESTINATION_MAX * raw_by_hour[hour].get(tract_id, 0.0) / destination_scale), 2)
            destination_base = round(min(DESTINATION_MAX, DESTINATION_MAX * base_by_hour[hour].get(tract_id, 0.0) / destination_scale), 2)
            weather_points = round(destination_points - destination_base, 2)
            score = round(min(100.0, max(0.0, population_points + commute_points + destination_points + road_points)), 1)
            hours[str(hour)] = {
                "score": score,
                "category": category_for(score),
                "population": population_points,
                "commute": commute_points,
                "destinations": destination_base,
                "roads": road_points,
                "weather": weather_points,
            }
        activity[tract_id] = hours
        no_vehicle = tract["share_households_no_vehicle"]
        age = tract["share_age_65_plus"]
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(tract.geometry),
                "properties": {
                    "id": tract_id,
                    "name": tract["name"],
                    "population": int(tract["population"] or 0),
                    "density": round(float(tract["density"]), 1),
                    "workers": profile["profile"]["workers"],
                    "morning_departure_share": profile["profile"]["morning_share"],
                    "evening_departure_share": profile["profile"]["evening_bin_share"],
                    "percent_no_vehicle": None if no_vehicle != no_vehicle else round(float(no_vehicle) * 100),
                    "percent_age_65_plus": None if age != age else round(float(age) * 100),
                    "destination_count": len(places_by_tract.get(tract_id, [])),
                    "road_count": int(road_counts.get(tract_id, 0)),
                },
            }
        )

    place_records = []
    for tract_id, items in places_by_tract.items():
        for place in items:
            place_records.append(
                {
                    "id": place["id_place"] if "id_place" in place.index else place["id"],
                    "name": place["name"],
                    "named": bool(place["named"]),
                    "category": place["category"],
                    "lat": place["lat"],
                    "lon": place["lon"],
                    "tract_id": tract_id,
                    "open": int(place["open"]),
                    "close": int(place["close"]),
                    "hours_source": place["hours_source"],
                }
            )
    place_records.sort(key=lambda item: item["name"])
    demo = next((place for place in place_records if place["name"].lower() == "crabtree valley mall"), None)
    if demo is None:
        demo = next((place for place in place_records if place["named"] and place["category"] == "shopping"), place_records[0])

    document = {"hours": HOURS, "scope": "Wake County", "day": "typical weekday", "demo_place_id": demo["id"], "tracts": activity}
    text = json.dumps(document)
    places_document = {"places": place_records}
    tracts_document = {"type": "FeatureCollection", "features": features}
    for folder in (ROOT / "data", ROOT / "web" / "public"):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "activity.json").write_text(text)
        (folder / "places.json").write_text(json.dumps(places_document))
        (folder / "wake-tracts.geojson").write_text(json.dumps(tracts_document))
    print(f"tracts {len(features)} places {len(place_records)} named {sum(place['named'] for place in place_records)}")
    print("demo", demo["name"], demo["category"], demo["tract_id"], demo["hours_source"], demo["open"], demo["close"])
    for hour in (8, 12, 16, 17, 18, 19, 20, 21):
        block = activity[demo["tract_id"]][str(hour)]
        print(f"  {hour} {block['score']} {block['category']} commute {block['commute']} dest {block['destinations']} weather {block['weather']}")


if __name__ == "__main__":
    main()
