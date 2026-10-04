"""Lookups and explanations for Fair Share. Numbers come from fairness.json."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from shapely.geometry import Point, shape

from api.settings import MODEL_URL, database_url, load_env
from pipeline.build_fairness import CITY_NAMES, sale_date, sale_year
from pipeline.fairness import assessment_gap, median, ratio
from pipeline.fetch_parcels import fetch_pin

# Wake reassesses every four years. The current roll took effect 1 Jan 2024,
# so a buyer inherits today's assessed value until the next countywide pass.
NEXT_REVALUATION = 2028
MIN_INHERIT_SALES = 8

ROOT = Path(__file__).resolve().parents[1]
FAIRNESS_PATH = ROOT / "data" / "fairness.json"
SALES_PATH = ROOT / "data" / "sales.json"
MAX_SALES_PER_TRACT = 400


def load_model() -> dict:
    fairness = json.loads(FAIRNESS_PATH.read_text())
    basis_year = fairness["county_stats"]["basis_year"]
    sales = [
        sale
        for sale in json.loads(SALES_PATH.read_text())["sales"]
        if sale.get("sale_year") == basis_year
    ]
    by_pin = {}
    by_tract: dict[str, list[dict]] = {}
    for sale in sales:
        by_pin[sale["pin"]] = sale
        by_tract.setdefault(sale["tract_id"], []).append(sale)
    return {
        "county": fairness["county_stats"],
        "tracts": fairness["tracts"],
        "sales": sales,
        "by_pin": by_pin,
        "by_tract": by_tract,
        "shapes": _shapes(),
    }


def _shapes() -> list[tuple[str, object]]:
    document = json.loads((ROOT / "data" / "wake-tracts.geojson").read_text())
    return [
        (feature["properties"]["id"], shape(feature["geometry"]))
        for feature in document["features"]
    ]


def locate_tract(model: dict, lat: float, lon: float) -> str | None:
    point = Point(lon, lat)
    for tract_id, geom in model["shapes"]:
        if geom.contains(point):
            return tract_id
    return None


def hydrate(model: dict, raw: dict) -> dict:
    city = (raw.get("city") or "").strip().upper()
    year = raw.get("sale_year") or sale_year(raw.get("sale_ms"))
    tract_id = raw.get("tract_id") or locate_tract(model, raw["lat"], raw["lon"]) or ""
    sale = {
        **raw,
        "city": CITY_NAMES.get(city, city),
        "sale_year": year,
        "sale_date": raw.get("sale_date") or sale_date(raw.get("sale_ms")),
        "tract_id": tract_id,
    }
    if sale["pin"] not in model["by_pin"]:
        model["by_pin"][sale["pin"]] = sale
        if tract_id:
            model["by_tract"].setdefault(tract_id, []).append(sale)
    return sale


def search(model: dict, query: str, limit: int = 8) -> list[dict]:
    text = " ".join(query.strip().lower().split())
    if len(text) < 3:
        return []
    found = []
    seen: set[str] = set()
    for sale in model["sales"]:
        label = f"{sale['address']} {sale['city']}".lower()
        if text in label:
            seen.add(sale["pin"])
            found.append({
                "pin": sale["pin"],
                "address": sale["address"],
                "city": sale["city"],
                "sale_date": sale["sale_date"],
            })
        if len(found) >= limit:
            return found
    return found


def _band_for(county: dict, price: float) -> dict | None:
    for band in county["bands"]:
        if band["low_price"] <= price <= band["high_price"]:
            return band
    return None


def parcel(model: dict, pin: str) -> dict:
    sale = model["by_pin"].get(pin)
    if sale is None:
        raw = fetch_pin(pin)
        if raw is None:
            raise KeyError(pin)
        year = raw.get("sale_year") or sale_year(raw.get("sale_ms"))
        if year != model["county"]["basis_year"]:
            raise KeyError(pin)
        sale = hydrate(model, raw)
    county = model["county"]
    tract = model["tracts"].get(sale.get("tract_id"), {
        "id": sale.get("tract_id"),
        "name": "Unknown tract",
        "median_ratio": None,
        "cod": None,
        "sales": 0,
        "relative_to_county": None,
        "enough_sales": False,
        "housing": {},
    })
    own_ratio = ratio(sale["assessed"], sale["price"])
    same_moment = sale.get("sale_year") == county["basis_year"]

    # What the home would be assessed at if it carried the ratio the county as
    # a whole carries, and the ratio its own price band carries.
    versus_county = assessment_gap(sale["assessed"], sale["price"], county["median_ratio"])
    band = _band_for(county, sale["price"])
    versus_band = (
        assessment_gap(sale["assessed"], sale["price"], band["median_ratio"]) if band else None
    )
    cheapest = county["bands"][0]["median_ratio"]
    tilt = assessment_gap(sale["assessed"], sale["price"], cheapest)

    return {
        "pin": sale["pin"],
        "address": sale["address"],
        "city": sale["city"],
        "lat": sale["lat"],
        "lon": sale["lon"],
        "assessed": sale["assessed"],
        "price": sale["price"],
        "sale_date": sale["sale_date"],
        "sale_year": sale.get("sale_year"),
        "same_moment": same_moment,
        "year_built": sale["year_built"],
        "heated_area": sale["heated_area"],
        "ratio": round(own_ratio, 4),
        "versus_county": versus_county,
        "versus_band": versus_band,
        "band": band,
        "cheapest_band_ratio": cheapest,
        "tilt": tilt,
        "tract": {
            "id": tract["id"],
            "name": tract["name"],
            "median_ratio": tract.get("median_ratio"),
            "cod": tract.get("cod"),
            "sales": tract.get("sales"),
            "relative_to_county": tract.get("relative_to_county"),
            "enough_sales": tract.get("enough_sales", False),
            "housing": tract.get("housing", {}),
        },
        "county": {
            "median_ratio": county["median_ratio"],
            "cod": county["cod"],
            "prd": county["prd"],
            "prb": county["prb"],
            "uniformity": county["uniformity"],
            "regressivity": county["regressivity"],
            "basis_year": county["basis_year"],
            "sales": county["sales"],
        },
    }


def inherit(model: dict, budget: float) -> dict:
    """What a buyer at this budget would have stepped into in 2024.

    This is not a listing search and it is not a price forecast. It is the
    assessment a purchaser inherits until the next revaluation, measured on
    the sales that actually closed at or under the budget.
    """
    try:
        ceiling = float(budget)
    except (TypeError, ValueError) as error:
        raise ValueError("budget must be a number") from error
    if ceiling < 50_000:
        raise ValueError("budget must be at least 50000")

    county = model["county"]
    basis = model["county"]["basis_year"]
    matched = [
        sale for sale in model["sales"]
        if sale["price"] <= ceiling and sale.get("sale_year") == basis
    ]
    ratios = [ratio(sale["assessed"], sale["price"]) for sale in matched]
    typical = median(ratios) if ratios else None

    by_tract: dict[str, list[dict]] = {}
    for sale in matched:
        by_tract.setdefault(sale["tract_id"], []).append(sale)

    neighborhoods = []
    for tract_id, sales in by_tract.items():
        if len(sales) < MIN_INHERIT_SALES:
            continue
        row = model["tracts"].get(tract_id, {})
        tract_ratios = [ratio(sale["assessed"], sale["price"]) for sale in sales]
        tract_ratio = median(tract_ratios)
        neighborhoods.append({
            "id": tract_id,
            "name": row.get("name", tract_id),
            "sales": len(sales),
            "median_ratio": round(tract_ratio, 4),
            "median_price": round(median([sale["price"] for sale in sales])),
            "relative_to_county": (
                round(100.0 * (tract_ratio / county["median_ratio"] - 1.0), 1)
                if county["median_ratio"]
                else None
            ),
        })
    neighborhoods.sort(key=lambda item: (-item["median_ratio"], -item["sales"]))

    return {
        "budget": ceiling,
        "next_revaluation": NEXT_REVALUATION,
        "sales": len(matched),
        "median_ratio": round(typical, 4) if typical is not None else None,
        "county_median_ratio": county["median_ratio"],
        "heavier_than_county": bool(typical is not None and typical > county["median_ratio"]),
        "neighborhoods": neighborhoods[:6],
        "neighborhoods_total": len(neighborhoods),
    }


def tract(model: dict, tract_id: str) -> dict:
    row = model["tracts"].get(tract_id)
    if row is None:
        raise KeyError(tract_id)
    sales = model["by_tract"].get(tract_id, [])
    points = [
        {
            "pin": sale["pin"],
            "address": sale["address"],
            "lat": sale["lat"],
            "lon": sale["lon"],
            "ratio": round(ratio(sale["assessed"], sale["price"]), 4),
            "price": sale["price"],
            "sale_date": sale["sale_date"],
        }
        for sale in sales[:MAX_SALES_PER_TRACT]
    ]
    return {
        **row,
        "points": points,
        "points_shown": len(points),
        "points_total": len(sales),
        "county_median_ratio": model["county"]["median_ratio"],
    }


def _facts(detail: dict) -> dict:
    county = detail["county"]
    gap = detail["versus_county"]
    return {
        "address": detail["address"],
        "sale_price": detail["price"],
        "assessed_value": detail["assessed"],
        "sale_date": detail["sale_date"],
        "this_home_ratio": detail["ratio"],
        "county_median_ratio": county["median_ratio"],
        "county_basis_year": county["basis_year"],
        "county_sales_analysed": county["sales"],
        "county_uniformity": county["uniformity"],
        "county_regressivity_verdict": county["regressivity"],
        "county_cod": county["cod"],
        "assessed_dollars_above_county_typical": gap["difference"],
        "percent_above_county_typical": gap["percent"],
        "price_band_median_ratio": detail["band"]["median_ratio"] if detail["band"] else None,
        "cheapest_band_median_ratio": detail["cheapest_band_ratio"],
        "tract_name": detail["tract"]["name"],
        "tract_median_ratio": detail["tract"]["median_ratio"],
        "tract_sales_analysed": detail["tract"]["sales"],
    }


def _fallback(detail: dict) -> str:
    gap = detail["versus_county"]
    direction = "above" if gap["difference"] > 0 else "below"
    return (
        f"This home sold for ${detail['price']:,.0f} and is assessed at ${detail['assessed']:,.0f}, "
        f"a ratio of {detail['ratio']:.3f}. The typical Wake County ratio is "
        f"{detail['county']['median_ratio']:.3f}, so the assessment sits "
        f"${abs(gap['difference']):,.0f} {direction} the county norm."
    )


def explain(model: dict, pin: str) -> dict:
    detail = parcel(model, pin)
    fallback = _fallback(detail)
    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"reply": fallback, "source": "fallback", "parcel": detail}
    prompt = (
        "You are explaining a property tax assessment ratio to the homeowner in two short spoken sentences. "
        "Use only the facts below and do not invent a tax rate, a tax bill, a dollar amount of tax owed, "
        "an appeal deadline, or any figure not listed. "
        "A sales ratio is the county assessed value divided by the actual sale price. "
        "A ratio above the county median means this home is assessed more heavily relative to what it sold for. "
        "Say plainly whether this home is assessed above or below the county norm, and state the difference "
        "as a dollar amount of assessed value without repeating the words 'assessed dollars'. "
        "If the cheapest price band has a higher median ratio than this home's own price band, mention that "
        "lower priced homes in Wake County carry a higher ratio. "
        "Do not tell the homeowner they will win an appeal.\n"
        f"Facts: {_facts(detail)}"
    )
    try:
        response = requests.post(
            MODEL_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        response.raise_for_status()
        reply = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError, TypeError) as error:
        print(f"gemini unavailable, using the written facts: {error}", flush=True)
        return {"reply": fallback, "source": "fallback", "parcel": detail}
    if not reply:
        return {"reply": fallback, "source": "fallback", "parcel": detail}
    return {"reply": reply, "source": "gemini", "parcel": detail}


def bands(model: dict) -> dict:
    """The price-band ratios, stored in Tiger when it is reachable."""
    county = model["county"]
    rows = list(county["bands"])
    url = database_url()
    if not url:
        return {"source": "fairness.json", "bands": rows, "basis_year": county["basis_year"]}
    try:
        _store(url, county["basis_year"], rows)
    except Exception as error:
        message = str(error).replace(url, "TIGER_DATABASE_URL")
        print(f"tiger unavailable, using fairness.json: {message}", flush=True)
        return {"source": "fairness.json", "bands": rows, "basis_year": county["basis_year"]}
    return {"source": "tiger", "bands": rows, "basis_year": county["basis_year"]}


def _store(url: str, basis_year: int, rows: list[dict]) -> None:
    import psycopg

    observed_at = datetime(basis_year, 1, 1, tzinfo=timezone.utc)
    with psycopg.connect(url, connect_timeout=8, autocommit=True) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ratio_band (
                band smallint NOT NULL,
                observed_at timestamptz NOT NULL,
                low_price double precision NOT NULL,
                high_price double precision NOT NULL,
                median_ratio double precision NOT NULL,
                sales integer NOT NULL,
                PRIMARY KEY (band, observed_at)
            )
            """
        )
        for row in rows:
            connection.execute(
                """
                INSERT INTO ratio_band (band, observed_at, low_price, high_price, median_ratio, sales)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (band, observed_at)
                DO UPDATE SET median_ratio = EXCLUDED.median_ratio, sales = EXCLUDED.sales
                """,
                (
                    row["band"],
                    observed_at,
                    row["low_price"],
                    row["high_price"],
                    row["median_ratio"],
                    row["sales"],
                ),
            )
