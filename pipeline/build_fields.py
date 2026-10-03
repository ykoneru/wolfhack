"""Build Triangle athletic fields and score each hour from ground heat and air.

A field crosses the line only when pavement-adjusted temperature and AirNow
air, together, are high enough. One of those alone can stay under the line.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.rules import FIELD_LINE, HOURS, field_parts  # noqa: E402

TRACTS_PATH = ROOT / "data" / "tracts.geojson"
RAW_PATH = ROOT / "data" / "raw" / "pitches.json"
OUT_DATA = ROOT / "data" / "fields.json"
OUT_WEB = ROOT / "web" / "public" / "fields.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
QUERY = """
[out:json][timeout:50];
(
  node["leisure"="pitch"](35.68,-79.08,36.08,-78.48);
  way["leisure"="pitch"](35.68,-79.08,36.08,-78.48);
);
out center;
"""
LINE = FIELD_LINE


def load_pitches() -> list[dict]:
    if RAW_PATH.exists() and RAW_PATH.stat().st_size > 0:
        payload = json.loads(RAW_PATH.read_text())
    else:
        response = requests.post(
            OVERPASS,
            data={"data": QUERY},
            headers={"User-Agent": "field-call wolfhack (ykoneru@ncsu.edu)", "Accept": "*/*"},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
        RAW_PATH.write_text(json.dumps(payload))
    pitches = []
    seen = set()
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        if element["type"] == "node":
            lat, lon = element.get("lat"), element.get("lon")
        else:
            center = element.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue
        key = (round(lat, 4), round(lon, 4))
        if key in seen:
            continue
        seen.add(key)
        pitches.append(
            {
                "id": f"osm-{element['type']}-{element['id']}",
                "name": tags.get("name"),
                "sport": (tags.get("sport") or "athletic").split(";")[0],
                "lat": lat,
                "lon": lon,
            }
        )
    return pitches


def hour_label(hour: int) -> str:
    clock = hour if hour <= 12 else hour - 12
    suffix = "am" if hour < 12 else "pm"
    return f"{clock}{suffix}"


def main() -> None:
    pitches = load_pitches()
    tracts = gpd.read_file(TRACTS_PATH)
    points = gpd.GeoDataFrame(pitches, geometry=[Point(item["lon"], item["lat"]) for item in pitches], crs="EPSG:4326")
    inside = gpd.sjoin(points, tracts, how="left", predicate="within", lsuffix="field", rsuffix="tract")
    missing = inside["index_tract"].isna()
    if missing.any():
        centroids = tracts.copy()
        centroids["geometry"] = tracts.geometry.centroid
        nearest = gpd.sjoin_nearest(
            points.loc[missing], centroids, how="left", lsuffix="field", rsuffix="tract"
        )
        for column in ("index_tract", "id_tract", "name_tract", "population", "share_age_65_plus", "hourly", "aqi", "land_cover"):
            inside.loc[missing, column] = nearest[column].to_numpy()
    fields = []
    for _, row in inside.drop_duplicates("id_field").iterrows():
        hourly_raw = row["hourly"] if isinstance(row["hourly"], dict) else json.loads(row["hourly"])
        land = row["land_cover"]
        if isinstance(land, str):
            land = json.loads(land)
        if not isinstance(land, dict):
            land = {}
        aqi = row["aqi"]
        if aqi != aqi:
            aqi = None
        aqi_value = None if aqi is None else float(aqi)
        hourly = {}
        for hour in HOURS:
            block = hourly_raw[str(hour)]
            temperature = float(block["temperature_f"])
            forecast = float(block.get("forecast_f", temperature))
            sky, ground, air, index = field_parts(forecast, temperature, aqi_value)
            hourly[str(hour)] = {
                "label": hour_label(hour),
                "forecast_f": round(forecast, 1),
                "temperature_f": round(temperature, 1),
                "sky": round(sky, 4),
                "ground": round(ground, 4),
                "air": round(air, 4),
                "index": round(index, 4),
                "crossed": index >= LINE,
            }
        sport = str(row["sport"]).replace("_", " ")
        raw_name = row["name_field"]
        named = isinstance(raw_name, str) and bool(raw_name.strip())
        name = raw_name if named else f"{sport.title()} field"
        age = row["share_age_65_plus"]
        population = row["population"]
        fields.append(
            {
                "id": row["id_field"],
                "name": name,
                "named": named,
                "sport": sport,
                "lat": round(float(row["lat"]), 5),
                "lon": round(float(row["lon"]), 5),
                "tract_id": row["id_tract"],
                "tract_name": None if row["name_tract"] != row["name_tract"] else row["name_tract"],
                "population_around": 0 if population != population else int(population),
                "percent_age_65_plus": None if age != age or age is None else round(float(age) * 100),
                "land_cover": (land or {}).get("label"),
                "aqi": None if aqi is None else round(float(aqi), 1),
                "hourly": hourly,
            }
        )
    fields.sort(key=lambda item: item["name"])
    document = {"line": LINE, "hours": HOURS, "fields": fields}
    text = json.dumps(document)
    OUT_DATA.write_text(text)
    OUT_WEB.parent.mkdir(parents=True, exist_ok=True)
    OUT_WEB.write_text(text)
    crossed = sum(1 for field in fields if any(block["crossed"] for block in field["hourly"].values()))
    print(f"wrote {len(fields)} fields, {crossed} cross the line in at least one hour")


if __name__ == "__main__":
    main()
