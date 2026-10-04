"""Download Wake County single-family sales with their assessed values.

Source: Wake County Property/Parcels FeatureServer. Each record carries the
county assessed value, the recorded sale price, and the parcel centroid, which
is what a sales-ratio study needs. Raw pages stay in data/raw so the build can
run without the network.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = RAW / "wake-sales.json"

SERVICE = "https://maps.wakegov.com/arcgis/rest/services/Property/Parcels/FeatureServer/0/query"
# Wake County's most recent revaluation took effect January 1, 2024, so sales
# from 2024 onward are the window that matches the current assessed values.
SALE_WINDOW_START = "2024-01-01"
WHERE = (
    "TYPE_USE_DECODE = 'SINGLFAM' "
    "AND TOTSALPRICE > 50000 "
    f"AND SALE_DATE >= DATE '{SALE_WINDOW_START}' "
    "AND TOTAL_VALUE_ASSD > 0"
)
FIELDS = [
    "PIN_NUM",
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
USER_AGENT = "fair-share wolfhack (ykoneru@ncsu.edu)"


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
    """Look up a 2024 single-family sale by street."""
    text = " ".join(query.strip().upper().split())
    if len(text) < 3:
        return []
    safe = text.replace("'", "''")
    response = requests.get(
        SERVICE,
        params={
            "where": (
                "TYPE_USE_DECODE = 'SINGLFAM' "
                "AND TOTSALPRICE > 50000 "
                "AND TOTAL_VALUE_ASSD > 0 "
                "AND SALE_DATE >= DATE '2024-01-01' "
                "AND SALE_DATE < DATE '2025-01-01' "
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
    found = []
    for feature in response.json().get("features") or []:
        row = record(feature)
        if row:
            found.append(row)
    return found


def record(feature: dict) -> dict | None:
    attributes = feature.get("attributes") or {}
    centroid = feature.get("centroid") or {}
    pin = attributes.get("PIN_NUM")
    assessed = attributes.get("TOTAL_VALUE_ASSD")
    price = attributes.get("TOTSALPRICE")
    lon = centroid.get("x")
    lat = centroid.get("y")
    if not pin or not assessed or not price or lon is None or lat is None:
        return None
    sale_ms = attributes.get("SALE_DATE")
    return {
        "pin": str(pin),
        "assessed": float(assessed),
        "price": float(price),
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
    print(f"Wake single-family sales since {SALE_WINDOW_START}: {total}", flush=True)
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
        time.sleep(0.2)
    OUT.write_text(json.dumps({"source": SERVICE, "sale_window_start": SALE_WINDOW_START, "sales": records}))
    print(f"wrote {OUT} with {len(records)} sales", flush=True)


if __name__ == "__main__":
    main()
