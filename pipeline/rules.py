"""Shared scoring rules for Last Door. Keep these in sync with web/src/rules.js."""

from __future__ import annotations

import math

RADIUS_MILES = 3.0
EXPOSED_BURDEN_MIN = 0.40
HEAT_FLOOR_F = 75.0
HEAT_SPAN_F = 35.0
AQI_SPAN = 200.0
WALK_MPH = 3.0
HOURS = [14, 15, 16, 17, 18, 19, 20]
BURDEN_WEIGHTS = {"vulnerability": 0.5, "heat": 0.35, "air": 0.15}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def heat_risk(temperature_f: float) -> float:
    return clamp((temperature_f - HEAT_FLOOR_F) / HEAT_SPAN_F)


def air_risk(aqi: float) -> float:
    return clamp(aqi / AQI_SPAN)


def vulnerability(share_age_65_plus: float, poverty_rate: float, share_households_no_vehicle: float) -> float:
    return (share_age_65_plus + poverty_rate + share_households_no_vehicle) / 3.0


def burden(share_age_65_plus: float, poverty_rate: float, share_households_no_vehicle: float, temperature_f: float, aqi: float) -> float:
    vuln = vulnerability(share_age_65_plus, poverty_rate, share_households_no_vehicle)
    return (
        BURDEN_WEIGHTS["vulnerability"] * vuln
        + BURDEN_WEIGHTS["heat"] * heat_risk(temperature_f)
        + BURDEN_WEIGHTS["air"] * air_risk(aqi)
    )


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 3958.7613
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def is_open(site: dict, hour: int, committed_site_ids: set[str] | None = None) -> bool:
    if site["id"] in (committed_site_ids or set()):
        return True
    close_hour = site.get("close_hour")
    if close_hour is None:
        return True
    return hour < close_hour


def is_exposed(burden_value: float) -> bool:
    return burden_value >= EXPOSED_BURDEN_MIN
