"""Pull Wake for-sale listings from RentCast. Only missing queries spend a call.

The website never calls RentCast. Run this by hand:

    .venv/bin/python pipeline/fetch_listings.py

Cities already in data/listings.json are skipped. After the city list is
complete, one extra daysOld=1:30 pull is allowed for Raleigh and Fuquay
Varina so the first 500 stale rows do not hide new listings. Later runs
exit before any HTTP. There is no --force.
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.settings import load_env  # noqa: E402
from pipeline.listings import (  # noqa: E402
    CITIES,
    DAYS_OLD,
    LISTINGS_PATH,
    LOCK_PATH,
    MAX_CALLS,
    MONTHLY_FREE,
    cached_cities,
    cached_recent_cities,
    clip_cache_to_wake,
    close_rentcast_cache,
    fetch_is_closed,
    listings_in_wake,
    load_listings,
    missing_cities,
    missing_recent_cities,
    slim_listing,
    write_week_stamp,
)

SALE_URL = "https://api.rentcast.io/v1/listings/sale"


def fetch_city(api_key: str, city: str, days_old: str | None = None) -> list[dict]:
    params = {
        "city": city,
        "state": "NC",
        "propertyType": "Single Family",
        "limit": 500,
        "offset": 0,
    }
    if days_old:
        params["daysOld"] = days_old
    response = requests.get(
        SALE_URL,
        params=params,
        headers={"X-Api-Key": api_key, "Accept": "application/json"},
        timeout=60,
    )
    if response.status_code == 401:
        raise RuntimeError("RentCast rejected the key. Check RENTCAST_API_KEY in .env")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected RentCast payload for {city}")
    return payload


def save_progress(payload: dict) -> None:
    payload["listings"] = listings_in_wake(payload.get("listings") or [])
    LISTINGS_PATH.write_text(json.dumps(payload))
    write_week_stamp(payload["fetched_at"], payload.get("calls_used") or 0, len(payload["listings"]))


def merge_city(listings: list[dict], seen: set[str], raw: list[dict]) -> int:
    kept = 0
    for row in raw:
        slim = slim_listing(row)
        if not slim or slim["key"] in seen:
            continue
        seen.add(slim["key"])
        listings.append(slim)
        kept += 1
    return kept


def main() -> None:
    load_env()
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing = load_listings()
        used = int(existing.get("calls_used") or 0)
        if fetch_is_closed(existing) or used >= MAX_CALLS:
            print(
                f"RentCast is closed ({used} calls used). No RentCast call made.",
                flush=True,
            )
            return
        todo = missing_cities(existing)
        recent_todo = missing_recent_cities(existing)
        if not todo and not recent_todo:
            close_rentcast_cache()
            dropped = clip_cache_to_wake()
            extra = f" Removed {dropped} pins outside Wake." if dropped else ""
            print(
                f"already have all {len(CITIES)} Wake cities and the {DAYS_OLD}-day refill "
                f"({len(existing.get('listings', []))} listings, {used} calls). "
                f"No RentCast call made.{extra}",
                flush=True,
            )
            return
        budget = max(0, MAX_CALLS - used)
        if budget <= 0:
            print(
                f"monthly cap of {MAX_CALLS} calls already used. No RentCast call made.",
                flush=True,
            )
            return

        api_key = os.environ.get("RENTCAST_API_KEY", "").strip()
        if not api_key:
            raise SystemExit("RENTCAST_API_KEY is empty. Add it to .env, then run this script.")

        print(
            f"missing cities: {', '.join(todo) or 'none'}. "
            f"recent refill: {', '.join(recent_todo) or 'none'}. "
            f"at most {budget} more of {MONTHLY_FREE}.",
            flush=True,
        )
        fetched_at = datetime.now(timezone.utc).isoformat()
        calls = used
        listings = list(existing.get("listings") or [])
        seen = {row.get("key") for row in listings if row.get("key")}
        done_cities = cached_cities(existing)
        done_recent = cached_recent_cities(existing)
        added = 0

        def persist() -> None:
            save_progress(
                {
                    "fetched_at": fetched_at,
                    "calls_used": calls,
                    "source": "RentCast /listings/sale",
                    "cities": done_cities,
                    "days_old_cities": done_recent,
                    "listings": listings,
                }
            )

        try:
            for city in todo:
                if calls >= MAX_CALLS or added >= budget:
                    print(f"hit the {MAX_CALLS}-call cap, stopping", flush=True)
                    break
                raw = fetch_city(api_key, city)
                calls += 1
                added += 1
                kept = merge_city(listings, seen, raw)
                done_cities.append(city)
                persist()
                print(
                    f"  {city}: {len(raw)} returned, {kept} new  (call {calls}/{MAX_CALLS})",
                    flush=True,
                )
            for city in recent_todo:
                if calls >= MAX_CALLS or added >= budget:
                    print(f"hit the {MAX_CALLS}-call cap, stopping", flush=True)
                    break
                raw = fetch_city(api_key, city, DAYS_OLD)
                calls += 1
                added += 1
                kept = merge_city(listings, seen, raw)
                done_recent.append(city)
                persist()
                print(
                    f"  {city} daysOld={DAYS_OLD}: {len(raw)} returned, {kept} new  "
                    f"(call {calls}/{MAX_CALLS})",
                    flush=True,
                )
        except requests.RequestException as error:
            print(f"RentCast stopped after {added} new call(s): {error}", flush=True)
            if added == 0 and not listings:
                raise SystemExit(1) from error
            persist()
            print("kept the cities that did arrive", flush=True)

        leftover = missing_cities({"cities": done_cities})
        leftover_recent = missing_recent_cities({"days_old_cities": done_recent})
        print(
            f"wrote {LISTINGS_PATH} with {len(listings_in_wake(listings))} Wake listings. "
            f"used {calls} of {MONTHLY_FREE} free calls total ({added} this run). "
            + (
                "All planned queries cached. Later runs spend nothing."
                if not leftover and not leftover_recent
                else f"Still missing: {', '.join(leftover + leftover_recent)}."
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
