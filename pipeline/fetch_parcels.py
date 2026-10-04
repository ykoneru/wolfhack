"""Download Wake County single-family parcels with land and building values.

Source: Wake County Property/Parcels FeatureServer. Each record already
splits the 2024 assessment into land and structure. Raw pages stay in
data/raw so the build can run without the network.
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

from pipeline.address import query_forms  # noqa: E402
RAW = ROOT / "data" / "raw"
OUT = RAW / "wake-homes.json"

SERVICE = "https://maps.wakegov.com/arcgis/rest/services/Property/Parcels/FeatureServer/0/query"
WHERE = (
    "TYPE_USE_DECODE = 'SINGLFAM' "
    "AND LAND_VAL > 0 "
    "AND BLDG_VAL > 0 "
    "AND TOTAL_VALUE_ASSD > 0 "
    "AND SITE_ADDRESS IS NOT NULL"
)
FIELDS = [
    "PIN_NUM",
    "LAND_VAL",
    "BLDG_VAL",
    "TOTAL_VALUE_ASSD",
    "TOTSALPRICE",
    "SALE_DATE",
    "YEAR_BUILT",
    "HEATEDAREA",
    "SITE_ADDRESS",
    "CITY_DECODE",
    "PLANNING_JURISDICTION",
]
PAGE = 2000
USER_AGENT = "house-or-lot wolfhack (ykoneru@ncsu.edu)"


def count() -> int:
    response = requests.get(
        SERVICE,
        params={"where": WHERE, "returnCountOnly": "true", "f": "json"},
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    response.raise_for_status()
    return int(response.json()["count"])


def page(offset: int) -> dict:
    response = requests.get(
        SERVICE,
        params={
            "where": WHERE,
            "outFields": ",".join(FIELDS),
            "orderByFields": "OBJECTID",
            "resultOffset": offset,
            "resultRecordCount": PAGE,
            "returnGeometry": "false",
            "returnCentroid": "true",
            "outSR": "4326",
            "f": "json",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def fetch_pin(pin: str) -> dict | None:
    safe = str(pin).replace("'", "''")
    response = requests.get(
        SERVICE,
        params={
            "where": f"PIN_NUM = '{safe}'",
            "outFields": ",".join(FIELDS),
            "returnGeometry": "false",
            "returnCentroid": "true",
            "outSR": "4326",
            "resultRecordCount": 1,
            "f": "json",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    features = response.json().get("features") or []
    return record(features[0]) if features else None


def search_address(query: str, limit: int = 8) -> list[dict]:
    """Look up any single-family house by street."""
    forms = [form.upper() for form in query_forms(query)]
    if not forms:
        return []
    found = []
    seen: set[str] = set()
    for form in forms:
        if len(form) < 3:
            continue
        safe = form.replace("'", "''")
        response = requests.get(
            SERVICE,
            params={
                "where": (
                    "TYPE_USE_DECODE = 'SINGLFAM' "
                    "AND LAND_VAL > 0 "
                    "AND BLDG_VAL > 0 "
                    "AND TOTAL_VALUE_ASSD > 0 "
                    f"AND UPPER(SITE_ADDRESS) LIKE '%{safe}%'"
                ),
                "outFields": ",".join(FIELDS),
                "returnGeometry": "false",
                "returnCentroid": "true",
                "outSR": "4326",
                "resultRecordCount": limit,
                "f": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
        for feature in response.json().get("features") or []:
            row = record(feature)
            if row and row["pin"] not in seen:
                seen.add(row["pin"])
                found.append(row)
            if len(found) >= limit:
                return found
    return found


def fetch_geometry(pin: str) -> dict | None:
    """Parcel outline in WGS84, when Wake GIS has one."""
    safe = str(pin).replace("'", "''")
    response = requests.get(
        SERVICE,
        params={
            "where": f"PIN_NUM = '{safe}'",
            "outFields": "PIN_NUM",
            "returnGeometry": "true",
            "outSR": "4326",
            "resultRecordCount": 1,
            "f": "geojson",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    features = payload.get("features") or []
    if not features:
        return None
    return features[0].get("geometry")


def record(feature: dict) -> dict | None:
    attributes = feature.get("attributes") or {}
    centroid = feature.get("centroid") or {}
    pin = attributes.get("PIN_NUM")
    land = attributes.get("LAND_VAL")
    building = attributes.get("BLDG_VAL")
    assessed = attributes.get("TOTAL_VALUE_ASSD")
    lon = centroid.get("x")
    lat = centroid.get("y")
    if not pin or not land or not building or not assessed or lon is None or lat is None:
        return None
    sale_ms = attributes.get("SALE_DATE")
    price = attributes.get("TOTSALPRICE")
    return {
        "pin": str(pin),
        "land": float(land),
        "building": float(building),
        "assessed": float(assessed),
        "price": float(price) if price else None,
        "sale_ms": int(sale_ms) if sale_ms else None,
        "year_built": attributes.get("YEAR_BUILT"),
        "heated_area": attributes.get("HEATEDAREA"),
        "address": (attributes.get("SITE_ADDRESS") or "").strip(),
        "city": (attributes.get("CITY_DECODE") or attributes.get("PLANNING_JURISDICTION") or "").strip(),
        "lat": round(float(lat), 6),
        "lon": round(float(lon), 6),
    }


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    total = count()
    print(f"Wake single-family homes with a land/building split: {total}", flush=True)
    records: list[dict] = []
    seen: set[str] = set()
    offset = 0
    while offset < total:
        payload = page(offset)
        features = payload.get("features") or []
        if not features:
            break
        for feature in features:
            row = record(feature)
            if row and row["pin"] not in seen:
                seen.add(row["pin"])
                records.append(row)
        offset += len(features)
        print(f"  {offset}/{total} fetched, {len(records)} usable", flush=True)
        time.sleep(0.15)
    OUT.write_text(json.dumps({"source": SERVICE, "homes": records}))
    print(f"wrote {OUT} with {len(records)} homes", flush=True)


if __name__ == "__main__":
    main()
