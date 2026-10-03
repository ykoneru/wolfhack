"""Estimated activity for a typical weekday in Wake County.

The score is a weighted sum, not a live crowd count. Commute timing comes from
ACS table B08302. Destination timing comes from OpenStreetMap hours when they
parse, otherwise from a documented category default.
"""

from __future__ import annotations

HOURS = list(range(8, 23))
POPULATION_MAX = 20.0
COMMUTE_MAX = 25.0
DESTINATION_MAX = 30.0
ROAD_MAX = 15.0

BASE_WEIGHT = {
    "restaurant": 1.2,
    "cafe": 1.0,
    "grocery": 1.3,
    "gym": 1.0,
    "shopping": 1.8,
    "school": 1.5,
    "university": 2.0,
    "bar": 1.3,
    "entertainment": 1.5,
    "park": 0.8,
    "hospital": 1.1,
    "fast_food": 1.1,
    "library": 0.8,
}

# Weekday defaults used only when OpenStreetMap hours are missing. Close is exclusive.
DEFAULT_HOURS = {
    "cafe": (7, 19),
    "restaurant": (11, 22),
    "fast_food": (10, 22),
    "grocery": (7, 23),
    "gym": (6, 22),
    "shopping": (10, 21),
    "school": (7, 16),
    "university": (8, 21),
    "bar": (16, 24),
    "entertainment": (12, 23),
    "park": (6, 21),
    "hospital": (0, 24),
    "library": (9, 20),
}

# Hour-specific multipliers. A closed place still contributes nothing.
HOUR_MULTIPLIER = {
    "morning": {
        "cafe": 1.8, "school": 1.8, "university": 1.8, "gym": 1.5, "grocery": 0.8,
        "restaurant": 0.5, "fast_food": 0.8, "park": 0.7, "shopping": 0.5, "bar": 0.0,
        "entertainment": 0.3, "hospital": 1.0, "library": 0.7,
    },
    "midday": {
        "restaurant": 1.6, "fast_food": 1.4, "university": 1.3, "shopping": 1.2,
        "cafe": 1.0, "grocery": 1.0, "park": 1.0, "gym": 0.8, "school": 1.1, "bar": 0.3,
        "entertainment": 0.8, "hospital": 1.0, "library": 1.0,
    },
    "evening": {
        "grocery": 1.6, "restaurant": 1.5, "gym": 1.4, "shopping": 1.6, "fast_food": 1.3,
        "university": 0.8, "cafe": 0.6, "park": 1.0, "bar": 1.2, "entertainment": 1.2,
        "school": 0.2, "hospital": 1.0, "library": 0.7,
    },
    "night": {
        "restaurant": 1.2, "bar": 1.8, "entertainment": 1.6, "fast_food": 1.1, "grocery": 0.4,
        "gym": 0.3, "shopping": 0.25, "cafe": 0.2, "park": 0.15, "university": 0.25,
        "school": 0.0, "hospital": 0.8, "library": 0.15,
    },
}


def category_for(score: float) -> str:
    if score <= 25:
        return "Quiet"
    if score <= 45:
        return "Light"
    if score <= 65:
        return "Moderate"
    if score <= 80:
        return "Busy"
    return "Very Busy"


def day_part(hour: int) -> str:
    if hour <= 10:
        return "morning"
    if hour <= 14:
        return "midday"
    if hour <= 18:
        return "evening"
    return "night"


def hour_multiplier(category: str, hour: int) -> float:
    return HOUR_MULTIPLIER[day_part(hour)].get(category, 0.5)


def clock_label(hour: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    shown = hour if 1 <= hour <= 12 else hour - 12
    if hour == 0:
        shown = 12
    return f"{shown}:00 {suffix}"


def weather_multiplier(temperature_f: float | None, aqi: float | None) -> tuple[float, bool]:
    """Adjust outdoor places only. Rain is not in the stored forecast, so it is not applied."""
    if temperature_f is None:
        return 1.0, False
    multiplier = 1.0
    if temperature_f >= 90:
        multiplier *= 0.90
    elif 65 <= temperature_f <= 82:
        multiplier *= 1.10
    if aqi is not None and aqi >= 101:
        multiplier *= 0.90
    return multiplier, True


def visit_fits(hour: int, open_hour: int, close_hour: int, minimum_minutes: int) -> bool:
    if hour < open_hour:
        return False
    return hour * 60 + minimum_minutes <= close_hour * 60


def best_hour(
    series: dict,
    open_hour: int,
    close_hour: int,
    earliest: int,
    latest: int,
    minimum_minutes: int,
) -> dict | None:
    """Lowest estimated activity that still leaves a usable visit."""
    chosen = None
    for hour in range(earliest, latest + 1):
        if str(hour) not in series:
            continue
        if not visit_fits(hour, open_hour, close_hour, minimum_minutes):
            continue
        block = series[str(hour)]
        if chosen is None or block["score"] < chosen["score"]:
            chosen = {"hour": hour, "score": block["score"], "category": block["category"]}
    return chosen


def p95(values: list[float]) -> float:
    if not values:
        return 1.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return ordered[index] or 1.0
