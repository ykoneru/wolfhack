"""Download ACS housing tables for Wake County tracts.

Median owner value, tenure, and rent burden give the context a ratio study
needs: who owns, who rents, and who is already stretched by housing cost.
Census Reporter serves the same American Community Survey tables the Census
API does and needs no key.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = RAW / "housing.json"

URL = "https://api.censusreporter.org/1.0/data/show/latest"
TABLES = ["B25077", "B25003", "B25070"]
WAKE_TRACTS = "140|05000US37183"
USER_AGENT = "fair-share wolfhack (ykoneru@ncsu.edu)"

# Renters paying 30 percent or more of income, the federal cost-burden line.
BURDENED_COLUMNS = [
    "B25070007",
    "B25070008",
    "B25070009",
    "B25070010",
]


def fetch() -> dict:
    response = requests.get(
        URL,
        params={"table_ids": ",".join(TABLES), "geo_ids": WAKE_TRACTS},
        headers={"User-Agent": USER_AGENT},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def tract_rows(payload: dict) -> dict:
    rows = {}
    for geo_id, blocks in payload["data"].items():
        tract_id = geo_id.replace("14000US", "")
        value = blocks["B25077"]["estimate"]["B25077001"]
        tenure = blocks["B25003"]["estimate"]
        rent = blocks["B25070"]["estimate"]
        households = tenure["B25003001"] or 0
        owners = tenure["B25003002"] or 0
        renters = tenure["B25003003"] or 0
        rent_total = rent["B25070001"] or 0
        burdened = sum(rent[column] or 0 for column in BURDENED_COLUMNS)
        rows[tract_id] = {
            "median_home_value": None if value is None else round(value),
            "households": round(households),
            "owner_occupied": round(owners),
            "renter_occupied": round(renters),
            "owner_share": round(owners / households, 4) if households else None,
            "renters_counted_for_burden": round(rent_total),
            "renters_cost_burdened": round(burdened),
            "renter_burden_share": round(burdened / rent_total, 4) if rent_total else None,
        }
    return rows


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    payload = fetch()
    rows = tract_rows(payload)
    release = payload.get("release", {}).get("name", "American Community Survey")
    OUT.write_text(json.dumps({"release": release, "tables": TABLES, "tracts": rows}))
    print(f"wrote {OUT} with {len(rows)} tracts from {release}", flush=True)
    with_value = sum(1 for row in rows.values() if row["median_home_value"])
    print(f"tracts with a median owner value: {with_value}", flush=True)


if __name__ == "__main__":
    main()
