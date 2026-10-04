"""Cached RentCast sale listings. The website never calls RentCast."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.address import canonical_address

ROOT = Path(__file__).resolve().parents[1]
LISTINGS_PATH = ROOT / "data" / "listings.json"
TRACTS_PATH = ROOT / "data" / "wake-tracts.geojson"
STAMP_PATH = ROOT / "data" / ".rentcast-week"
LOCK_PATH = ROOT / "data" / "listings.lock"
FRESH_DAYS = 7
MAX_CALLS = 14
MONTHLY_FREE = 50
MAX_ON_MARKET_DAYS = 30
DAYS_OLD = "1:30"
RECENT_FILL_CITIES = (
    "Raleigh",
    "Fuquay Varina",
)
CITIES = (
    "Raleigh",
    "Cary",
    "Apex",
    "Holly Springs",
    "Wake Forest",
    "Garner",
    "Fuquay-Varina",
    "Knightdale",
    "Morrisville",
    "Wendell",
    "Zebulon",
    "Rolesville",
)


def empty_cache() -> dict:
    return {"fetched_at": None, "calls_used": 0, "source": "RentCast /listings/sale", "listings": []}


def load_listings(path: Path = LISTINGS_PATH) -> dict:
    if not path.exists():
        return empty_cache()
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return empty_cache()
    if not isinstance(payload, dict):
        return empty_cache()
    payload.setdefault("listings", [])
    return payload


def cache_age(payload: dict, now: datetime | None = None) -> timedelta | None:
    stamp = payload.get("fetched_at")
    if not stamp:
        return None
    fetched = datetime.fromisoformat(stamp)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    moment = now or datetime.now(timezone.utc)
    return moment - fetched


def cache_is_fresh(payload: dict, now: datetime | None = None, days: int = FRESH_DAYS) -> bool:
    age = cache_age(payload, now)
    return age is not None and age < timedelta(days=days)


def load_stamp(path: Path = STAMP_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _stamp_datetime(payload: dict) -> datetime | None:
    stamp = payload.get("fetched_at")
    if not stamp:
        return None
    fetched = datetime.fromisoformat(stamp)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return fetched


def same_calendar_month(payload: dict, now: datetime | None = None) -> bool:
    fetched = _stamp_datetime(payload)
    if fetched is None:
        return False
    moment = now or datetime.now(timezone.utc)
    return (fetched.year, fetched.month) == (moment.year, moment.month)


def already_fetched_this_week(
    now: datetime | None = None,
    listings_path: Path = LISTINGS_PATH,
    stamp_path: Path = STAMP_PATH,
) -> dict | None:
    """Any successful fetch this week blocks another RentCast call."""
    listings = load_listings(listings_path)
    if cache_is_fresh(listings, now):
        return listings
    stamp = load_stamp(stamp_path)
    if cache_is_fresh(stamp, now):
        return stamp
    return None


def already_spent_this_month(
    now: datetime | None = None,
    listings_path: Path = LISTINGS_PATH,
    stamp_path: Path = STAMP_PATH,
) -> dict | None:
    """Any spend in this calendar month blocks another RentCast call."""
    listings = load_listings(listings_path)
    if same_calendar_month(listings, now):
        return listings
    stamp = load_stamp(stamp_path)
    if same_calendar_month(stamp, now):
        return stamp
    return None


def cached_cities(payload: dict) -> list[str]:
    return [str(city) for city in payload.get("cities") or [] if str(city).strip()]


def missing_cities(payload: dict | None = None, cities: tuple[str, ...] = CITIES) -> list[str]:
    payload = payload if payload is not None else load_listings()
    have = {city.strip().lower() for city in cached_cities(payload)}
    return [city for city in cities if city.lower() not in have]


def cached_recent_cities(payload: dict) -> list[str]:
    return [str(city) for city in payload.get("days_old_cities") or [] if str(city).strip()]


def missing_recent_cities(
    payload: dict | None = None,
    cities: tuple[str, ...] = RECENT_FILL_CITIES,
) -> list[str]:
    payload = payload if payload is not None else load_listings()
    have = {city.strip().lower() for city in cached_recent_cities(payload)}
    return [city for city in cities if city.lower() not in have]


def fetch_is_closed(payload: dict | None = None) -> bool:
    if payload is not None:
        return bool(payload.get("closed"))
    if load_listings().get("closed"):
        return True
    return bool(load_stamp().get("closed"))


def close_rentcast_cache(path: Path = LISTINGS_PATH) -> dict:
    """Permanently stop RentCast pulls. Disk only."""
    payload = load_listings(path)
    payload["closed"] = True
    path.write_text(json.dumps(payload))
    write_week_stamp(
        payload.get("fetched_at") or datetime.now(timezone.utc).isoformat(),
        int(payload.get("calls_used") or 0),
        len(payload.get("listings") or []),
    )
    stamp = load_stamp()
    stamp["closed"] = True
    STAMP_PATH.write_text(json.dumps(stamp))
    return payload


def write_week_stamp(fetched_at: str, calls_used: int, count: int, path: Path = STAMP_PATH) -> None:
    stamp = load_stamp(path)
    stamp.update({"fetched_at": fetched_at, "calls_used": calls_used, "count": count})
    path.write_text(json.dumps(stamp))


def listed_in_last_days(
    row: dict,
    days: int = MAX_ON_MARKET_DAYS,
    now: datetime | None = None,
) -> bool:
    """True when RentCast says the home hit the market within `days`. Disk only."""
    dom = row.get("days_on_market")
    if isinstance(dom, (int, float)):
        return 0 <= float(dom) <= days
    stamp = row.get("listed_date")
    if not stamp:
        return False
    try:
        listed = datetime.fromisoformat(str(stamp))
    except ValueError:
        return False
    if listed.tzinfo is None:
        listed = listed.replace(tzinfo=timezone.utc)
    moment = now or datetime.now(timezone.utc)
    age = moment - listed
    return timedelta(0) <= age <= timedelta(days=days)


def recent_listings(
    listings: list[dict],
    days: int = MAX_ON_MARKET_DAYS,
    now: datetime | None = None,
) -> list[dict]:
    return [row for row in listings if listed_in_last_days(row, days, now)]


_wake_shape = None


def wake_shape():
    """Union of Wake census tracts. Local file only."""
    global _wake_shape
    if _wake_shape is None:
        from shapely.geometry import shape
        from shapely.ops import unary_union

        document = json.loads(TRACTS_PATH.read_text())
        _wake_shape = unary_union([shape(feature["geometry"]) for feature in document["features"]])
    return _wake_shape


def inside_wake(row: dict) -> bool:
    lat = row.get("lat")
    lon = row.get("lon")
    if lat is None or lon is None:
        return False
    from shapely.geometry import Point

    return bool(wake_shape().covers(Point(float(lon), float(lat))))


def listings_in_wake(listings: list[dict]) -> list[dict]:
    return [row for row in listings if inside_wake(row)]


def clip_cache_to_wake(path: Path = LISTINGS_PATH) -> int:
    """Drop cached pins outside Wake. Does not call RentCast."""
    payload = load_listings(path)
    before = len(payload.get("listings") or [])
    kept = listings_in_wake(payload.get("listings") or [])
    if len(kept) == before:
        return 0
    payload["listings"] = kept
    path.write_text(json.dumps(payload))
    return before - len(kept)


def listing_key(address: str, city: str = "") -> str:
    return canonical_address(f"{address} {city}".strip())


def slim_listing(raw: dict) -> dict | None:
    street = (raw.get("addressLine1") or "").strip()
    city = (raw.get("city") or "").strip()
    if not street:
        return None
    if (raw.get("status") or "").strip() != "Active":
        return None
    county = (raw.get("county") or "").strip()
    if county and county.lower() != "wake":
        return None
    return {
        "id": raw.get("id"),
        "address": street,
        "city": city.upper(),
        "key": listing_key(street, city),
        "price": raw.get("price"),
        "listed_date": (raw.get("listedDate") or "")[:10] or None,
        "days_on_market": raw.get("daysOnMarket"),
        "lat": raw.get("latitude"),
        "lon": raw.get("longitude"),
        "property_type": raw.get("propertyType"),
    }


def index_listings(listings: list[dict]) -> dict[str, dict]:
    by_key = {}
    for row in listings:
        key = row.get("key") or listing_key(row.get("address", ""), row.get("city", ""))
        if key:
            by_key[key] = row
    return by_key


def find_listing(listings: list[dict], address: str, city: str = "") -> dict | None:
    if not listings:
        return None
    by_key = index_listings(listings)
    for candidate in (listing_key(address, city), listing_key(address)):
        if candidate in by_key:
            return by_key[candidate]
    needle = canonical_address(address)
    if not needle:
        return None
    for row in listings:
        if needle and needle in (row.get("key") or ""):
            return row
    return None


def public_listing(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "address": row.get("address"),
        "city": row.get("city"),
        "price": row.get("price"),
        "listed_date": row.get("listed_date"),
        "days_on_market": row.get("days_on_market"),
        "lat": row.get("lat"),
        "lon": row.get("lon"),
        "source": "RentCast",
    }
