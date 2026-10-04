"""Lookups for Parcel. Numbers come from land.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from shapely.geometry import Point, shape

from api.settings import MODEL_URL, load_env
from pipeline.build_land import CITY_NAMES, sale_date, sale_year
from pipeline.land import (
    LOT_SHARE,
    TEARDOWN_YEAR,
    advice,
    classify,
    land_share,
    median,
    verdict_label,
)
from pipeline.address import address_matches, query_forms
from pipeline.fetch_parcels import fetch_geometry, fetch_pin, search_address
from pipeline.listings import (
    MAX_ON_MARKET_DAYS,
    find_listing,
    index_listings,
    listing_key,
    listings_in_wake,
    load_listings,
    public_listing,
    recent_listings,
)

ROOT = Path(__file__).resolve().parents[1]
LAND_PATH = ROOT / "data" / "land.json"
HOMES_PATH = ROOT / "data" / "homes.json"
MAX_HOMES_PER_TRACT = 400


def load_model() -> dict:
    land = json.loads(LAND_PATH.read_text())
    homes = json.loads(HOMES_PATH.read_text())["homes"]
    by_pin = {}
    by_tract: dict[str, list[dict]] = {}
    for home in homes:
        by_pin[home["pin"]] = home
        by_tract.setdefault(home["tract_id"], []).append(home)
    return {
        "county": land["county_stats"],
        "tracts": land["tracts"],
        "homes": homes,
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
    share = raw.get("land_share")
    if share is None:
        share = land_share(raw["land"], raw["building"])
    kind = raw.get("verdict") or classify(share, raw.get("year_built"))
    tract_id = raw.get("tract_id") or locate_tract(model, raw["lat"], raw["lon"]) or ""
    home = {
        **raw,
        "city": CITY_NAMES.get(city, city),
        "sale_year": year,
        "sale_date": raw.get("sale_date") or sale_date(raw.get("sale_ms")),
        "tract_id": tract_id,
        "land_share": share,
        "verdict": kind,
    }
    if home["pin"] not in model["by_pin"]:
        model["by_pin"][home["pin"]] = home
        if tract_id:
            model["by_tract"].setdefault(tract_id, []).append(home)
    return home


def search(model: dict, query: str, limit: int = 8) -> list[dict]:
    forms = query_forms(query)
    if not forms or len(forms[0]) < 3:
        return []
    found = []
    seen: set[str] = set()
    for home in model["homes"]:
        if address_matches(query, home["address"], home.get("city") or ""):
            seen.add(home["pin"])
            found.append(_match(home))
        if len(found) >= limit:
            return found
    try:
        remote = search_address(query, limit)
    except requests.RequestException as error:
        print(f"parcel search unavailable: {error}", flush=True)
        if not found:
            raise
        return found
    for raw in remote:
        if raw["pin"] in seen:
            continue
        home = hydrate(model, raw)
        found.append(_match(home))
        if len(found) >= limit:
            break
    return found


def _cached_sale_rows() -> list[dict]:
    return recent_listings(listings_in_wake(load_listings().get("listings", [])))


def _listing_for(address: str, city: str = "") -> dict | None:
    return public_listing(find_listing(_cached_sale_rows(), address, city))


def _match(home: dict) -> dict:
    listing = _listing_for(home["address"], home.get("city") or "")
    return {
        "pin": home["pin"],
        "address": home["address"],
        "city": home["city"],
        "verdict": home.get("verdict"),
        "year_built": home.get("year_built"),
        "for_sale": bool(listing),
    }


def parcel(model: dict, pin: str) -> dict:
    home = model["by_pin"].get(pin)
    if home is None:
        raw = fetch_pin(pin)
        if raw is None:
            raise KeyError(pin)
        home = hydrate(model, raw)
    county = model["county"]
    tract = model["tracts"].get(home.get("tract_id"), {
        "id": home.get("tract_id"),
        "name": "Unknown tract",
        "median_land_share": None,
        "homes": 0,
        "relative_to_county": None,
        "enough_homes": False,
        "housing": {},
    })
    share = home.get("land_share") or land_share(home["land"], home["building"])
    kind = home.get("verdict") or classify(share, home.get("year_built"))
    versus = None
    if tract.get("median_land_share"):
        versus = round(100.0 * (share / tract["median_land_share"] - 1.0), 1)
    return {
        "pin": home["pin"],
        "address": home["address"],
        "city": home["city"],
        "lat": home["lat"],
        "lon": home["lon"],
        "land": home["land"],
        "building": home["building"],
        "assessed": home["assessed"],
        "price": home.get("price"),
        "sale_date": home.get("sale_date"),
        "sale_year": home.get("sale_year"),
        "year_built": home.get("year_built"),
        "heated_area": home.get("heated_area"),
        "land_share": round(share, 4),
        "verdict": kind,
        "verdict_label": verdict_label(kind),
        "advice": advice(kind),
        "versus_tract": versus,
        "tract": {
            "id": tract.get("id"),
            "name": tract.get("name"),
            "median_land_share": tract.get("median_land_share"),
            "median_land": tract.get("median_land"),
            "median_building": tract.get("median_building"),
            "homes": tract.get("homes"),
            "relative_to_county": tract.get("relative_to_county"),
            "enough_homes": tract.get("enough_homes", False),
            "house_count": tract.get("house_count"),
            "lot_count": tract.get("lot_count"),
            "teardown_count": tract.get("teardown_count"),
            "housing": tract.get("housing", {}),
        },
        "geometry": _parcel_geometry(home),
        "listing": _listing_for(home["address"], home.get("city") or ""),
        "county": {
            "median_land_share": county["median_land_share"],
            "homes": county["homes"],
            "house_count": county["house_count"],
            "lot_count": county["lot_count"],
            "teardown_count": county["teardown_count"],
            "lot_threshold": county.get("lot_threshold", LOT_SHARE),
            "teardown_year": county.get("teardown_year", TEARDOWN_YEAR),
        },
    }


def hotspots(model: dict, limit: int = 6) -> dict:
    """Tracts where the lot, not the house, is the typical purchase."""
    rows = []
    for row in model["tracts"].values():
        if not row.get("enough_homes"):
            continue
        rows.append({
            "id": row["id"],
            "name": row["name"],
            "homes": row["homes"],
            "median_land_share": row["median_land_share"],
            "lot_count": row.get("lot_count", 0),
            "teardown_count": row.get("teardown_count", 0),
            "relative_to_county": row.get("relative_to_county"),
        })
    rows.sort(key=lambda item: (-item["median_land_share"], -item["teardown_count"]))
    county = model["county"]
    return {
        "meaning": (
            "These neighborhoods have the highest typical land share. "
            "That is useful if you want land, and useful if you want to know you are not mainly buying a house."
        ),
        "county_median_land_share": county["median_land_share"],
        "neighborhoods": rows[:limit],
        "neighborhoods_total": len(rows),
    }


def tract(model: dict, tract_id: str) -> dict:
    row = model["tracts"].get(tract_id)
    if row is None:
        raise KeyError(tract_id)
    homes = model["by_tract"].get(tract_id, [])
    ranked = sorted(homes, key=lambda home: (0 if home["verdict"] != "house" else 1, -home["land_share"]))
    points = [
        {
            "pin": home["pin"],
            "address": home["address"],
            "lat": home["lat"],
            "lon": home["lon"],
            "land_share": round(home["land_share"], 4),
            "verdict": home["verdict"],
            "year_built": home.get("year_built"),
        }
        for home in ranked[:MAX_HOMES_PER_TRACT]
    ]
    return {
        **row,
        "points": points,
        "points_shown": len(points),
        "points_total": len(homes),
        "county_median_land_share": model["county"]["median_land_share"],
    }


def explain(model: dict, pin: str) -> dict:
    detail = parcel(model, pin)
    fallback = _fallback(detail)
    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"reply": fallback, "source": "fallback", "parcel": detail}
    prompt = (
        "You are explaining whether a buyer is purchasing a house or a lot. "
        "Use two short spoken sentences and only the facts below. "
        "Do not invent a tax rate, a list price, or a rebuild cost. "
        "Say the verdict, the land share, and what that means for a remodel or a teardown.\n"
        f"Facts: { _facts(detail) }"
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


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and value == value


def discover_homes(model: dict) -> dict:
    """Compact home index for Discover. For-sale flags reuse the on-disk listing cache."""
    sale_index = index_listings(_cached_sale_rows())
    homes = []
    for home in model["homes"]:
        assessed = home.get("assessed")
        share = home.get("land_share")
        lat = home.get("lat")
        lon = home.get("lon")
        if not _finite(assessed) or assessed <= 0:
            continue
        if not _finite(share):
            continue
        if not _finite(lat) or not _finite(lon):
            continue
        address = home.get("address") or ""
        city = home.get("city") or ""
        for_sale = listing_key(address, city) in sale_index or listing_key(address) in sale_index
        homes.append(
            {
                "pin": home["pin"],
                "address": home.get("address") or "",
                "lat": lat,
                "lon": lon,
                "assessed": assessed,
                "land_share": round(float(share), 4),
                "tract_id": home.get("tract_id") or "",
                "for_sale": for_sale,
            }
        )
    return {
        "homes": homes,
        "sale_count": sum(1 for home in homes if home["for_sale"]),
    }


def _land_share_by_listing_key(model: dict | None) -> dict[str, float]:
    index = {}
    for home in (model or {}).get("homes") or []:
        share = home.get("land_share")
        if not _finite(share):
            continue
        address = home.get("address") or ""
        city = home.get("city") or ""
        value = float(share)
        for key in (listing_key(address, city), listing_key(address)):
            if key:
                index[key] = value
    return index


def listings(model: dict | None = None) -> dict:
    """Read the on-disk RentCast cache. Never calls RentCast."""
    payload = load_listings()
    shares = _land_share_by_listing_key(model)
    rows = []
    for row in recent_listings(listings_in_wake(payload.get("listings", []))):
        item = public_listing(row)
        if not item:
            continue
        key = listing_key(row.get("address") or "", row.get("city") or "")
        share = shares.get(key) or shares.get(listing_key(row.get("address") or ""))
        if share is not None:
            item["land_share"] = round(share, 4)
        rows.append(item)
    return {
        "fetched_at": payload.get("fetched_at"),
        "source": payload.get("source") or "RentCast",
        "window_days": MAX_ON_MARKET_DAYS,
        "listings": rows,
    }


def cities(model: dict) -> dict:
    county = model["county"]
    return {
        "source": "land.json",
        "cities": county.get("cities", []),
        "median_land_share": county["median_land_share"],
    }


def _facts(detail: dict) -> dict:
    return {
        "address": detail["address"],
        "land_value": detail["land"],
        "building_value": detail["building"],
        "land_share": detail["land_share"],
        "verdict": detail["verdict_label"],
        "year_built": detail["year_built"],
        "advice": detail["advice"],
        "tract_name": detail["tract"]["name"],
        "tract_median_land_share": detail["tract"]["median_land_share"],
        "county_median_land_share": detail["county"]["median_land_share"],
    }


def _fallback(detail: dict) -> str:
    share = f"{detail['land_share'] * 100:.0f}"
    return (
        f"{detail['address']} is a {detail['verdict_label'].lower()}. "
        f"Land is {share} percent of the county split, "
        f"{advice(detail['verdict'])}"
    )


def _parcel_geometry(home: dict) -> dict | None:
    if home.get("geometry"):
        return home["geometry"]
    try:
        geometry = fetch_geometry(home["pin"])
    except requests.RequestException as error:
        print(f"parcel geometry unavailable: {error}", flush=True)
        return None
    if geometry:
        home["geometry"] = geometry
    return geometry


# Older server imports still name this inherit.
def inherit(model: dict, budget: float | None = None) -> dict:
    return hotspots(model)
