"""House-or-lot labels from Wake County's land and building values.

The county already splits every parcel. Land share is land divided by
land plus building. A high share means the market is paying for the lot.
"""

from __future__ import annotations

# Land at or above this share means the lot is the larger piece.
LOT_SHARE = 0.40
# An older house on a high-land-share lot is the teardown watch list.
TEARDOWN_YEAR = 1975
MIN_TRACT_HOMES = 25


def land_share(land: float, building: float) -> float:
    total = land + building
    if land < 0 or building < 0 or total <= 0:
        raise ValueError("land and building must be positive")
    return land / total


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("median needs at least one value")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def classify(share: float, year_built: int | None) -> str:
    """house, lot, or teardown — the call a buyer can act on."""
    if share >= LOT_SHARE and year_built and year_built <= TEARDOWN_YEAR:
        return "teardown"
    if share >= LOT_SHARE:
        return "lot"
    return "house"


def verdict_label(kind: str) -> str:
    return {
        "house": "House",
        "lot": "Lot",
        "teardown": "Teardown watch",
    }[kind]


def advice(kind: str) -> str:
    if kind == "teardown":
        return (
            "The lot is the larger piece and the house is older. If you want "
            "the land, that can be the point. If you want the house, a builder "
            "may be bidding on the same address."
        )
    if kind == "lot":
        return (
            "The lot is the larger piece. If you want land or location, that "
            "is the purchase. If you want to renovate the house, the market "
            "may not pay you back. Insurance rebuilds the building, not the land."
        )
    return (
        "The house is the larger piece. Condition and improvements matter "
        "more here than the size of the lot."
    )


def is_home(row: dict) -> bool:
    if row.get("land", 0) <= 0 or row.get("building", 0) <= 0:
        return False
    if not (row.get("address") or "").strip():
        return False
    if row.get("lat") is None or row.get("lon") is None:
        return False
    return True
