"""Run the assessment ratio study for Wake County and write the map files.

Every 2024 single-family sale is matched to
the census tract it sits in, then summarised with the measures assessors are
judged by. Output goes to data/ and web/public/.
"""

from __future__ import annotations

import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fairness import (  # noqa: E402
    COD_MAX,
    MEDIAN_RATIO_RANGE,
    MIN_TRACT_SALES,
    PRB_RANGE,
    PRD_RANGE,
    assessment_gap,
    coefficient_of_dispersion,
    deciles,
    is_arms_length,
    is_lookup,
    median,
    price_related_bias,
    price_related_differential,
    ratio,
    regressivity_verdict,
    uniformity_verdict,
    weighted_mean_ratio,
)

TRACTS_PATH = ROOT / "data" / "tracts.geojson"
SALES_PATH = ROOT / "data" / "raw" / "wake-sales.json"
HOUSING_PATH = ROOT / "data" / "raw" / "housing.json"
WAKE = "37183"
REVALUATION = "2024-01-01"

# Wake's CITY_DECODE mixes full names with two-letter codes for the same town.
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


def load_sales() -> list[dict]:
    payload = json.loads(SALES_PATH.read_text())
    rows = []
    for sale in payload["sales"]:
        year = sale_year(sale["sale_ms"])
        city = (sale["city"] or "").strip().upper()
        rows.append({
            **sale,
            "city": CITY_NAMES.get(city, city),
            "sale_year": year,
            "sale_date": sale_date(sale["sale_ms"]),
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


def summarise(sales: list[dict]) -> dict:
    ratios = [ratio(sale["assessed"], sale["price"]) for sale in sales]
    return {
        "sales": len(sales),
        "median_ratio": round(median(ratios), 4),
        "cod": round(coefficient_of_dispersion(ratios), 2),
        "weighted_mean_ratio": round(weighted_mean_ratio(sales), 4),
        "median_price": round(median([sale["price"] for sale in sales])),
        "median_assessed": round(median([sale["assessed"] for sale in sales])),
    }


def main() -> None:
    raw_sales = load_sales()
    lookup = [sale for sale in raw_sales if is_lookup(sale)]
    kept = [sale for sale in lookup if is_arms_length(sale)]
    print(
        f"sales read {len(raw_sales)}, searchable {len(lookup)}, "
        f"arms-length {len(kept)}",
        flush=True,
    )

    tracts = wake_tracts()
    points = gpd.GeoDataFrame(
        lookup,
        geometry=[Point(sale["lon"], sale["lat"]) for sale in lookup],
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(points, tracts, how="inner", predicate="within", lsuffix="sale", rsuffix="tract")
    print(f"sales inside a Wake tract: {len(joined)}", flush=True)

    by_tract: dict[str, list[dict]] = defaultdict(list)
    for row in joined.to_dict("records"):
        by_tract[str(row["id"])].append({
            "pin": row["pin"],
            "assessed": float(row["assessed"]),
            "price": float(row["price"]),
            "address": row["address"],
            "city": row["city"],
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "sale_date": row["sale_date"],
            "sale_year": row["sale_year"],
            "year_built": row["year_built"],
            "heated_area": row["heated_area"],
        })

    matched = [sale for sales in by_tract.values() for sale in sales]

    # The equity measures use sales from the revaluation year, when assessed
    # value and market price describe the same moment.
    base_year = int(REVALUATION[:4])
    base = [
        sale for sale in matched
        if sale["sale_year"] == base_year and is_arms_length(sale)
    ]
    county = summarise(base)
    county_prd = price_related_differential(base)
    county_prb = price_related_bias(base)
    county.update({
        "prd": round(county_prd, 4),
        "prb": round(county_prb, 4),
        "uniformity": uniformity_verdict(county["cod"]),
        "regressivity": regressivity_verdict(county_prd, county_prb),
        "bands": deciles(base),
        "basis_year": base_year,
        "revaluation": REVALUATION,
        "standards": {
            "median_ratio": list(MEDIAN_RATIO_RANGE),
            "cod_max": COD_MAX,
            "prd": list(PRD_RANGE),
            "prb": list(PRB_RANGE),
        },
    })

    # How far the frozen assessment has drifted from the market since then.
    drift = []
    for year in sorted({sale["sale_year"] for sale in matched if sale["sale_year"]}):
        block = [
            sale for sale in matched
            if sale["sale_year"] == year and is_arms_length(sale)
        ]
        if len(block) < MIN_TRACT_SALES:
            continue
        drift.append({"year": year, **summarise(block)})
    county["drift"] = drift

    housing = json.loads(HOUSING_PATH.read_text())["tracts"]
    tract_rows = {}
    for tract in tracts.to_dict("records"):
        tract_id = str(tract["id"])
        sales = by_tract.get(tract_id, [])
        base_sales = [
            sale for sale in sales
            if sale["sale_year"] == base_year and is_arms_length(sale)
        ]
        row = {
            "id": tract_id,
            "name": tract["name"],
            "population": tract["population"],
            "sales_all_years": len(sales),
            "housing": housing.get(tract_id, {}),
        }
        if len(base_sales) >= MIN_TRACT_SALES:
            stats = summarise(base_sales)
            relative = stats["median_ratio"] / county["median_ratio"] - 1.0
            row.update({
                **stats,
                "relative_to_county": round(100.0 * relative, 1),
                "uniformity": uniformity_verdict(stats["cod"]),
                "enough_sales": True,
            })
        else:
            row.update({
                "sales": len(base_sales),
                "median_ratio": None,
                "relative_to_county": None,
                "enough_sales": False,
            })
        tract_rows[tract_id] = row

    graded = [row for row in tract_rows.values() if row["enough_sales"]]
    print(f"tracts with at least {MIN_TRACT_SALES} sales in {base_year}: {len(graded)} of {len(tract_rows)}", flush=True)

    fairness = {
        "county": "Wake County, North Carolina",
        "source": "Wake County Property/Parcels FeatureServer and ACS 2024 5-year",
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
                "median_ratio": row["median_ratio"],
                "relative_to_county": row["relative_to_county"],
                "sales": row.get("sales", 0),
                "enough_sales": row["enough_sales"],
            },
        })
    geojson = {"type": "FeatureCollection", "features": features}

    for folder in (DATA_OUT, WEB_OUT):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "fairness.json").write_text(json.dumps(fairness))
        (folder / "wake-tracts.geojson").write_text(json.dumps(geojson))

    # Searchable homes are 2024 sales only, so a house's ratio and the county
    # study describe the same assessment moment.
    sales_out = []
    for tract_id, sales in by_tract.items():
        for sale in sales:
            if sale["sale_year"] == base_year:
                sales_out.append({**sale, "tract_id": tract_id})
    sales_out.sort(key=lambda sale: sale["address"])
    (DATA_OUT / "sales.json").write_text(json.dumps({"sales": sales_out}))
    print(f"wrote {DATA_OUT / 'sales.json'} with {len(sales_out)} sales", flush=True)

    print("\ncounty ratio study")
    print(f"  basis year {county['basis_year']} ({county['sales']} sales)")
    print(f"  median ratio {county['median_ratio']}")
    print(f"  COD {county['cod']} -> {county['uniformity']}")
    print(f"  PRD {county['prd']}  PRB {county['prb']} -> {county['regressivity']}")
    print("\nmedian ratio by price band")
    for band in county["bands"]:
        print(f"  band {band['band']:>2} ${band['low_price']:>9,.0f}-${band['high_price']:>9,.0f}  ratio {band['median_ratio']}")
    print("\nmedian ratio by sale year")
    for row in county["drift"]:
        print(f"  {row['year']}  ratio {row['median_ratio']}  sales {row['sales']}")


if __name__ == "__main__":
    main()
