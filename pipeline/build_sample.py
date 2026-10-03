"""Write the step 0 sample fixtures and check that 2pm is covered and 5pm is not."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.rules import (  # noqa: E402
    EXPOSED_BURDEN_MIN,
    HOURS,
    RADIUS_MILES,
    air_risk,
    burden,
    haversine_miles,
    heat_risk,
    is_exposed,
    is_open,
)

SAMPLE_RATES = {
    "share_age_65_plus": 0.24,
    "poverty_rate": 0.58,
    "share_households_no_vehicle": 0.68,
}
SAMPLE_AQI = 90
SAMPLE_TEMPS = {14: 88, 15: 90, 16: 92, 17: 94, 18: 96, 19: 94, 20: 92}

TRACTS = [
    {"id": "sample-south", "name": "Sample South Raleigh", "population": 4500, "lat": 35.737, "lon": -78.638},
    {"id": "sample-south-2", "name": "Sample South Raleigh West", "population": 3900, "lat": 35.728, "lon": -78.648},
    {"id": "sample-southeast", "name": "Sample Southeast Raleigh", "population": 5100, "lat": 35.762, "lon": -78.582},
    {"id": "sample-southeast-2", "name": "Sample Southeast Raleigh East", "population": 2900, "lat": 35.752, "lon": -78.572},
    {"id": "sample-rex", "name": "Sample Rex", "population": 3600, "lat": 35.815, "lon": -78.700},
]

SITES = [
    {
        "id": "sample-south-library",
        "name": "Sample South Raleigh Library",
        "type": "library",
        "lat": 35.735,
        "lon": -78.640,
        "close_hour": 17,
        "hours_source": "osm",
    },
    {
        "id": "sample-southeast-center",
        "name": "Sample Southeast Community Center",
        "type": "community_centre",
        "lat": 35.760,
        "lon": -78.580,
        "close_hour": 17,
        "hours_source": "default",
    },
    {
        "id": "sample-rex-hospital",
        "name": "Sample Rex Hospital",
        "type": "hospital",
        "lat": 35.817,
        "lon": -78.703,
        "close_hour": None,
        "hours_source": "nconemap",
    },
]


def square(lon: float, lat: float, half: float = 0.006) -> list:
    ring = [
        [round(lon - half, 6), round(lat - half, 6)],
        [round(lon + half, 6), round(lat - half, 6)],
        [round(lon + half, 6), round(lat + half, 6)],
        [round(lon - half, 6), round(lat + half, 6)],
        [round(lon - half, 6), round(lat - half, 6)],
    ]
    return ring


def hourly_block() -> dict:
    block = {}
    for hour, temp in SAMPLE_TEMPS.items():
        value = burden(
            SAMPLE_RATES["share_age_65_plus"],
            SAMPLE_RATES["poverty_rate"],
            SAMPLE_RATES["share_households_no_vehicle"],
            temp,
            SAMPLE_AQI,
        )
        block[str(hour)] = {
            "temperature_f": temp,
            "heat_risk": round(heat_risk(temp), 4),
            "burden": round(value, 4),
        }
    return block


def tracts_geojson() -> dict:
    features = []
    for tract in TRACTS:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [square(tract["lon"], tract["lat"])]},
                "properties": {
                    "id": tract["id"],
                    "name": tract["name"],
                    "population": tract["population"],
                    **SAMPLE_RATES,
                    "centroid": [tract["lon"], tract["lat"]],
                    "aqi": SAMPLE_AQI,
                    "air_risk": round(air_risk(SAMPLE_AQI), 4),
                    "hourly": hourly_block(),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def sites_geojson() -> dict:
    features = []
    for site in SITES:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [site["lon"], site["lat"]]},
                "properties": {
                    "id": site["id"],
                    "name": site["name"],
                    "type": site["type"],
                    "close_hour": site["close_hour"],
                    "hours_source": site["hours_source"],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def score_hour(tract_features: list, site_features: list, hour: int, committed: set[str] | None = None) -> dict:
    sites = []
    for feature in site_features:
        lon, lat = feature["geometry"]["coordinates"]
        sites.append({**feature["properties"], "lat": lat, "lon": lon})

    open_sites = [site for site in sites if is_open(site, hour, committed)]
    tracts_out = {}
    uncovered_population = 0

    for feature in tract_features:
        props = feature["properties"]
        lon, lat = props["centroid"]
        hour_stats = props["hourly"][str(hour)]
        exposed = is_exposed(hour_stats["burden"])
        nearest = None
        if open_sites:
            nearest = min(open_sites, key=lambda site: haversine_miles(lat, lon, site["lat"], site["lon"]))
            distance = haversine_miles(lat, lon, nearest["lat"], nearest["lon"])
        else:
            distance = None
        covered = distance is not None and distance <= RADIUS_MILES
        uncovered = exposed and not covered
        if uncovered:
            uncovered_population += props["population"]
        tracts_out[props["id"]] = {
            "covered": covered,
            "exposed": exposed,
            "uncovered": uncovered,
            "nearest_site_id": None if nearest is None else nearest["id"],
            "distance_miles": None if distance is None else round(distance, 3),
            "burden": hour_stats["burden"],
        }

    return {"uncovered_population": uncovered_population, "tracts": tracts_out}


def people_saved_by(tract_features: list, site_features: list, hour: int, site_id: str, already_open: set[str]) -> int:
    before = score_hour(tract_features, site_features, hour, already_open)
    after = score_hour(tract_features, site_features, hour, already_open | {site_id})
    saved = 0
    for feature in tract_features:
        tract_id = feature["properties"]["id"]
        if before["tracts"][tract_id]["uncovered"] and not after["tracts"][tract_id]["uncovered"]:
            saved += feature["properties"]["population"]
    return saved


def recommend(tract_features: list, site_features: list, hour: int) -> dict:
    closed = []
    for feature in site_features:
        site = feature["properties"]
        if not is_open(site, hour):
            closed.append(site["id"])

    picked = []
    forced: set[str] = set()
    for _ in closed:
        best_id = None
        best_people = 0
        for site_id in closed:
            if site_id in forced:
                continue
            people = people_saved_by(tract_features, site_features, hour, site_id, forced)
            if people > best_people:
                best_id = site_id
                best_people = people
        if best_id is None:
            break
        forced.add(best_id)
        picked.append({"site_id": best_id, "people_added": best_people})

    return {
        "1": picked[:1],
        "3": picked[:3],
        "5": picked[:5],
    }


def hours_document(tract_collection: dict, site_collection: dict) -> dict:
    by_hour = {}
    for hour in HOURS:
        scored = score_hour(tract_collection["features"], site_collection["features"], hour)
        scored["recommendations"] = recommend(tract_collection["features"], site_collection["features"], hour)
        by_hour[str(hour)] = scored
    return {
        "radius_miles": RADIUS_MILES,
        "exposed_burden_min": EXPOSED_BURDEN_MIN,
        "hours": HOURS,
        "by_hour": by_hour,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> None:
    tracts = tracts_geojson()
    sites = sites_geojson()
    hours = hours_document(tracts, sites)
    for folder in (ROOT / "data" / "sample", ROOT / "web" / "public" / "sample"):
        write_json(folder / "tracts.geojson", tracts)
        write_json(folder / "sites.geojson", sites)
        write_json(folder / "hours.json", hours)

    two_pm = hours["by_hour"]["14"]["uncovered_population"]
    five_pm = hours["by_hour"]["17"]["uncovered_population"]
    if two_pm != 0 or five_pm <= two_pm:
        raise SystemExit(f"sample flip failed: 2pm uncovered={two_pm}, 5pm uncovered={five_pm}")
    print(f"wrote sample fixtures; uncovered population 2pm={two_pm}, 5pm={five_pm}")


if __name__ == "__main__":
    main()
