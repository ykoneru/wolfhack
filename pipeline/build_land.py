"""Join every Wake single-family home to its census tract and write the map.

Land share is the county's land value divided by land plus building. Output
goes to data/ and web/public/.
"""

from __future__ import annotations

import datetime
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.land import (  # noqa: E402
    LOT_SHARE,
    MIN_TRACT_HOMES,
    TEARDOWN_YEAR,
    classify,
    is_home,
    land_share,
    median,
)

TRACTS_PATH = ROOT / "data" / "tracts.geojson"
HOMES_PATH = ROOT / "data" / "raw" / "wake-homes.json"
HOUSING_PATH = ROOT / "data" / "raw" / "housing.json"
WAKE = "37183"
MAX_KEEP_PER_TRACT = 120

CITY_NAMES = {
    "AP": "APEX",
    "CA": "CARY",
    "FV": "FUQUAY-VARINA",
    "GA": "GARNER",
    "HS": "HOLLY SPRINGS",
    "KN": "KNIGHTDALE",
    "MO": "MORRISVILLE",
    "RA": "RALEIGH",
    "RO": "ROLESVILLE",
    "WC": "UNINCORPORATED WAKE",
    "WE": "WENDELL",
    "WF": "WAKE FOREST",
    "ZB": "ZEBULON",
}

DATA_OUT = ROOT / "data"
WEB_OUT = ROOT / "web" / "public"


def sale_year(sale_ms: int | None) -> int | None:
    if not sale_ms:
        return None
    moment = datetime.datetime.fromtimestamp(sale_ms / 1000, datetime.UTC)
    return moment.year


def sale_date(sale_ms: int | None) -> str | None:
    if not sale_ms:
        return None
    return datetime.datetime.fromtimestamp(sale_ms / 1000, datetime.UTC).date().isoformat()


def load_homes() -> list[dict]:
    payload = json.loads(HOMES_PATH.read_text())
    rows = []
    for home in payload["homes"]:
        if not is_home(home):
            continue
        city = (home["city"] or "").strip().upper()
        share = land_share(home["land"], home["building"])
        year = home.get("year_built")
        rows.append({
            **home,
            "city": CITY_NAMES.get(city, city),
            "sale_year": sale_year(home.get("sale_ms")),
            "sale_date": sale_date(home.get("sale_ms")),
            "land_share": share,
            "verdict": classify(share, year),
        })
    return rows


def wake_tracts() -> gpd.GeoDataFrame:
    document = json.loads(TRACTS_PATH.read_text())
    features = [
        feature for feature in document["features"]
        if str(feature["properties"].get("id", "")).startswith(WAKE)
    ]
    frame = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    return frame[["id", "name", "population", "geometry"]]


def keep_homes(homes: list[dict]) -> list[dict]:
    ranked = sorted(
        homes,
        key=lambda home: (
            0 if home["verdict"] == "teardown" else 1 if home["verdict"] == "lot" else 2,
            -home["land_share"],
            0 if home.get("price") else 1,
        ),
    )
    return ranked[:MAX_KEEP_PER_TRACT]


def summarise(homes: list[dict]) -> dict:
    shares = [home["land_share"] for home in homes]
    kinds = Counter(home["verdict"] for home in homes)
    return {
        "homes": len(homes),
        "median_land_share": round(median(shares), 4),
        "median_land": round(median([home["land"] for home in homes])),
        "median_building": round(median([home["building"] for home in homes])),
        "house_count": kinds["house"],
        "lot_count": kinds["lot"],
        "teardown_count": kinds["teardown"],
        "lot_share_of_homes": round((kinds["lot"] + kinds["teardown"]) / len(homes), 4),
    }


def main() -> None:
    raw = load_homes()
    print(f"homes read {len(raw)}", flush=True)

    tracts = wake_tracts()
    points = gpd.GeoDataFrame(
        raw,
        geometry=[Point(home["lon"], home["lat"]) for home in raw],
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(points, tracts, how="inner", predicate="within", lsuffix="home", rsuffix="tract")
    print(f"homes inside a Wake tract: {len(joined)}", flush=True)

    by_tract: dict[str, list[dict]] = defaultdict(list)
    for row in joined.to_dict("records"):
        by_tract[str(row["id"])].append({
            "pin": row["pin"],
            "land": float(row["land"]),
            "building": float(row["building"]),
            "assessed": float(row["assessed"]),
            "price": row["price"],
            "address": row["address"],
            "city": row["city"],
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "sale_date": row["sale_date"],
            "sale_year": row["sale_year"],
            "year_built": row["year_built"],
            "heated_area": row["heated_area"],
            "land_share": float(row["land_share"]),
            "verdict": row["verdict"],
        })

    matched = [home for homes in by_tract.values() for home in homes]
    county = summarise(matched)
    kinds = Counter(home["verdict"] for home in matched)
    by_city: dict[str, list[dict]] = defaultdict(list)
    for home in matched:
        if home["city"]:
            by_city[home["city"]].append(home)
    cities = []
    for city, homes in by_city.items():
        if len(homes) < MIN_TRACT_HOMES:
            continue
        cities.append({"city": city, **summarise(homes)})
    cities.sort(key=lambda row: (-row["median_land_share"], -row["homes"]))

    county.update({
        "lot_threshold": LOT_SHARE,
        "teardown_year": TEARDOWN_YEAR,
        "house_count": kinds["house"],
        "lot_count": kinds["lot"],
        "teardown_count": kinds["teardown"],
        "cities": cities,
        "revaluation": "2024-01-01",
    })

    housing = {}
    if HOUSING_PATH.exists():
        housing = json.loads(HOUSING_PATH.read_text())["tracts"]

    tract_rows = {}
    for tract in tracts.to_dict("records"):
        tract_id = str(tract["id"])
        homes = by_tract.get(tract_id, [])
        row = {
            "id": tract_id,
            "name": tract["name"],
            "population": tract["population"],
            "housing": housing.get(tract_id, {}),
        }
        if len(homes) >= MIN_TRACT_HOMES:
            stats = summarise(homes)
            relative = stats["median_land_share"] / county["median_land_share"] - 1.0
            row.update({
                **stats,
                "relative_to_county": round(100.0 * relative, 1),
                "enough_homes": True,
            })
        else:
            row.update({
                "homes": len(homes),
                "median_land_share": None,
                "relative_to_county": None,
                "enough_homes": False,
                "house_count": 0,
                "lot_count": 0,
                "teardown_count": 0,
            })
        tract_rows[tract_id] = row

    graded = [row for row in tract_rows.values() if row["enough_homes"]]
    print(f"tracts with at least {MIN_TRACT_HOMES} homes: {len(graded)} of {len(tract_rows)}", flush=True)

    land = {
        "county": "Wake County, North Carolina",
        "source": "Wake County Property/Parcels FeatureServer land and building values",
        "county_stats": county,
        "tracts": tract_rows,
    }
    features = []
    for tract in tracts.to_dict("records"):
        tract_id = str(tract["id"])
        row = tract_rows[tract_id]
        features.append({
            "type": "Feature",
            "geometry": json.loads(gpd.GeoSeries([tract["geometry"]], crs="EPSG:4326").to_json())["features"][0]["geometry"],
            "properties": {
                "id": tract_id,
                "name": tract["name"],
                "median_land_share": row["median_land_share"],
                "relative_to_county": row["relative_to_county"],
                "homes": row.get("homes", 0),
                "enough_homes": row["enough_homes"],
                "median_land": row.get("median_land"),
                "median_building": row.get("median_building"),
                "lot_count": row.get("lot_count", 0),
                "teardown_count": row.get("teardown_count", 0),
            },
        })
    geojson = {"type": "FeatureCollection", "features": features}

    homes_out = []
    for tract_id, homes in by_tract.items():
        for home in keep_homes(homes):
            homes_out.append({**home, "tract_id": tract_id})
    homes_out.sort(key=lambda home: home["address"])

    for folder in (DATA_OUT, WEB_OUT):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "land.json").write_text(json.dumps(land))
        (folder / "wake-tracts.geojson").write_text(json.dumps(geojson))
    (DATA_OUT / "homes.json").write_text(json.dumps({"homes": homes_out}))
    print(f"wrote {DATA_OUT / 'homes.json'} with {len(homes_out)} searchable homes", flush=True)

    print("\ncounty land split")
    print(f"  homes {county['homes']}")
    print(f"  median land share {county['median_land_share']}")
    print(f"  house {county['house_count']}  lot {county['lot_count']}  teardown {county['teardown_count']}")
    print("\nmedian land share by city")
    for row in cities[:8]:
        print(f"  {row['city']:<22} {row['median_land_share']:.3f}  n={row['homes']}")


if __name__ == "__main__":
    main()
