"""Raise afternoon temperatures slightly in paved counties using USGS NLCD land cover.

Samples one point per county from the MRLC NLCD 2021 land-cover service.
Developed medium and high intensity get a 10 percent temperature bump.
Forest and every other class stay on the National Weather Service forecast.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.rules import HOURS, heat_risk  # noqa: E402

TRACTS_PATH = ROOT / "data" / "tracts.geojson"
CACHE = ROOT / "data" / "raw" / "nlcd"
WMS = "https://www.mrlc.gov/geoserver/mrlc_display/wms"
LAYER = "NLCD_2021_Land_Cover_L48"
HEADERS = {"User-Agent": "last-door wolfhack (ykoneru@ncsu.edu)"}
PAVED = {23, 24}
LABELS = {
    11: "open water",
    21: "developed, open space",
    22: "developed, low intensity",
    23: "developed, medium intensity",
    24: "developed, high intensity",
    31: "barren",
    41: "deciduous forest",
    42: "evergreen forest",
    43: "mixed forest",
    52: "shrub",
    71: "grassland",
    81: "pasture",
    82: "crops",
    90: "woody wetlands",
    95: "emergent wetlands",
}


def county_points(features: list[dict]) -> dict[str, tuple[float, float]]:
    buckets: dict[str, list[tuple[float, float]]] = {}
    for feature in features:
        props = feature["properties"]
        lon, lat = props["centroid"]
        buckets.setdefault(props["id"][:5], []).append((lon, lat))
    return {
        county: (
            round(sum(item[0] for item in coords) / len(coords), 4),
            round(sum(item[1] for item in coords) / len(coords), 4),
        )
        for county, coords in buckets.items()
    }


def land_cover(lon: float, lat: float, county: str) -> int | None:
    path = CACHE / f"{county}.json"
    if path.exists() and path.stat().st_size > 0:
        payload = json.loads(path.read_text())
    else:
        pad = 0.001
        response = requests.get(
            WMS,
            params={
                "service": "WMS",
                "version": "1.1.1",
                "request": "GetFeatureInfo",
                "layers": LAYER,
                "query_layers": LAYER,
                "styles": "",
                "srs": "EPSG:4326",
                "bbox": f"{lon - pad},{lat - pad},{lon + pad},{lat + pad}",
                "width": 101,
                "height": 101,
                "x": 50,
                "y": 50,
                "info_format": "application/json",
                "feature_count": 1,
            },
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
        time.sleep(0.15)
    features = payload.get("features") or []
    if not features:
        return None
    value = features[0]["properties"].get("PALETTE_INDEX")
    return None if value is None else int(value)


def apply_bump(hourly: dict, code: int | None) -> None:
    factor = 1.10 if code in PAVED else 1.0
    for block in hourly.values():
        forecast = block.get("forecast_f", block["temperature_f"])
        block["forecast_f"] = forecast
        adjusted = round(forecast * factor, 1)
        block["temperature_f"] = adjusted
        block["heat_risk"] = round(heat_risk(adjusted), 4)


def main() -> None:
    tracts = json.loads(TRACTS_PATH.read_text())
    points = county_points(tracts["features"])
    covers: dict[str, int | None] = {}
    for index, (county, (lon, lat)) in enumerate(sorted(points.items()), start=1):
        try:
            covers[county] = land_cover(lon, lat, county)
        except requests.RequestException as error:
            print(f"skipped {county}: {error}")
            covers[county] = None
        if index % 20 == 0:
            print(f"sampled {index} of {len(points)} counties", flush=True)

    for feature in tracts["features"]:
        props = feature["properties"]
        code = covers.get(props["id"][:5])
        props["land_cover"] = None if code is None else {"code": code, "label": LABELS.get(code, "other")}
        if props.get("hourly"):
            apply_bump(props["hourly"], code)

    TRACTS_PATH.write_text(json.dumps(tracts) + "\n")
    paved = next(
        (
            feature["properties"]
            for feature in tracts["features"]
            if (feature["properties"].get("land_cover") or {}).get("code") in PAVED
            and "16" in feature["properties"].get("hourly", {})
        ),
        None,
    )
    forest = next(
        (
            feature["properties"]
            for feature in tracts["features"]
            if (feature["properties"].get("land_cover") or {}).get("code") in {41, 42, 43}
            and "16" in feature["properties"].get("hourly", {})
        ),
        None,
    )
    if paved is None or forest is None:
        raise SystemExit("could not find both a paved tract and a forest tract")
    paved_hour = paved["hourly"]["16"]
    forest_hour = forest["hourly"]["16"]
    print(f"paved {paved['id']} {paved['land_cover']['label']}: forecast {paved_hour['forecast_f']} F, adjusted {paved_hour['temperature_f']} F")
    print(f"forest {forest['id']} {forest['land_cover']['label']}: forecast {forest_hour['forecast_f']} F, adjusted {forest_hour['temperature_f']} F")
    if paved_hour["temperature_f"] <= paved_hour["forecast_f"]:
        raise SystemExit("paved tract was not warmed")
    if forest_hour["temperature_f"] != forest_hour["forecast_f"]:
        raise SystemExit("forest tract should keep the forecast temperature")


if __name__ == "__main__":
    main()
