"""Checks for the RentCast cache helpers. No network."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.listings import (
    CITIES,
    already_fetched_this_week,
    already_spent_this_month,
    cache_is_fresh,
    fetch_is_closed,
    find_listing,
    inside_wake,
    listed_in_last_days,
    listing_key,
    missing_cities,
    missing_recent_cities,
    recent_listings,
    same_calendar_month,
    slim_listing,
)


def main() -> None:
    now = datetime(2026, 10, 4, tzinfo=timezone.utc)
    fresh = {"fetched_at": (now - timedelta(days=2)).isoformat(), "listings": []}
    week_edge = {"fetched_at": (now - timedelta(days=7)).isoformat(), "listings": []}
    stale = {"fetched_at": (now - timedelta(days=8)).isoformat(), "listings": []}
    assert cache_is_fresh(fresh, now)
    assert not cache_is_fresh(week_edge, now)
    assert not cache_is_fresh(stale, now)
    assert not cache_is_fresh({"fetched_at": None}, now)
    scratch = Path("/tmp/parcel-listings-check")
    scratch.mkdir(exist_ok=True)
    listings_path = scratch / "listings.json"
    stamp_path = scratch / ".rentcast-week"
    listings_path.unlink(missing_ok=True)
    stamp_path.unlink(missing_ok=True)
    assert already_fetched_this_week(now, listings_path, stamp_path) is None
    listings_path.write_text('{"fetched_at": "%s", "listings": []}' % fresh["fetched_at"])
    assert already_fetched_this_week(now, listings_path, stamp_path) is not None
    listings_path.unlink()
    stamp_path.write_text('{"fetched_at": "%s"}' % fresh["fetched_at"])
    assert already_fetched_this_week(now, listings_path, stamp_path) is not None
    assert same_calendar_month(fresh, now)
    assert already_spent_this_month(now, listings_path, stamp_path) is not None
    later = {"fetched_at": datetime(2026, 11, 1, tzinfo=timezone.utc).isoformat()}
    assert not same_calendar_month(later, now)

    raw = {
        "id": "724-Toulouse-Ct",
        "addressLine1": "724 Toulouse Ct",
        "city": "Cary",
        "county": "Wake",
        "status": "Active",
        "price": 675000,
        "listedDate": "2026-09-01T00:00:00.000Z",
        "daysOnMarket": 12,
        "latitude": 35.7,
        "longitude": -78.8,
        "propertyType": "Single Family",
    }
    row = slim_listing(raw)
    assert row is not None
    assert row["city"] == "CARY"
    assert row["key"] == listing_key("724 Toulouse Ct", "Cary")
    assert slim_listing({**raw, "status": "Inactive"}) is None
    assert slim_listing({**raw, "county": "Durham"}) is None

    found = find_listing([row], "724 TOULOUSE COURT", "CARY")
    assert found is not None
    assert found["price"] == 675000
    assert find_listing([row], "1000 DOROTHEA DR", "RALEIGH") is None
    assert listed_in_last_days({"days_on_market": 12}, 30)
    assert not listed_in_last_days({"days_on_market": 87}, 30)
    assert len(recent_listings([row, {**row, "days_on_market": 400}])) == 1
    assert missing_cities({"cities": ["Raleigh", "Cary"]})[0] == "Apex"
    assert missing_cities({"cities": list(CITIES)}) == []
    assert missing_recent_cities({"days_old_cities": []})[0] == "Raleigh"
    assert missing_recent_cities({"days_old_cities": ["Raleigh", "Fuquay Varina"]}) == []
    assert fetch_is_closed({"closed": True})
    assert not fetch_is_closed({"closed": False, "fetched_at": None})
    assert inside_wake({"lat": 35.79, "lon": -78.65})
    assert not inside_wake({"lat": 36.2, "lon": -78.9})
    print("listings checks passed")


if __name__ == "__main__":
    main()
