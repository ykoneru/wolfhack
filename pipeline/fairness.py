"""Sales-ratio math for a property assessment study.

The measures are the ones assessors are held to: median ratio, COD for
uniformity, and PRD and PRB for regressivity. Thresholds come from the IAAO
Standard on Ratio Studies for single-family residential property.

A ratio is the county assessed value divided by what the home actually sold
for. A ratio above the local median means the home is carrying more assessed
value per dollar of market price than its neighbours.
"""

from __future__ import annotations

import math

# IAAO Standard on Ratio Studies, single-family residential.
MEDIAN_RATIO_RANGE = (0.90, 1.10)
COD_MAX = 15.0
PRD_RANGE = (0.98, 1.03)
PRB_RANGE = (-0.05, 0.05)

# A ratio this far from the middle is almost always a bundled deed, a family
# transfer, or a teardown rather than an open-market sale.
RATIO_FLOOR = 0.4
RATIO_CEILING = 2.0
MIN_TRACT_SALES = 15


def ratio(assessed: float, price: float) -> float:
    if price <= 0:
        raise ValueError("a sale price must be positive")
    return assessed / price


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("median needs at least one value")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def is_lookup(sale: dict) -> bool:
    """A sold house with enough fields to search and place on the map.

    The 2024 ratio study is stricter and also requires an arm's-length sale.
    """
    if sale["price"] <= 50_000 or sale["assessed"] <= 0:
        return False
    if not (sale.get("address") or "").strip():
        return False
    if sale.get("lat") is None or sale.get("lon") is None:
        return False
    return True


def is_arms_length(sale: dict) -> bool:
    """Keep open-market sales of houses that already existed when assessed."""
    if sale["price"] <= 50_000 or sale["assessed"] <= 0:
        return False
    value = ratio(sale["assessed"], sale["price"])
    if not RATIO_FLOOR <= value <= RATIO_CEILING:
        return False
    if sale.get("year_built") and sale.get("sale_year"):
        # The assessment predates a house finished in or after the sale year.
        if sale["year_built"] >= sale["sale_year"]:
            return False
    return True


def coefficient_of_dispersion(ratios: list[float]) -> float:
    """Average spread around the median, as a percentage. Lower is more even."""
    center = median(ratios)
    if center == 0:
        raise ValueError("the median ratio is zero")
    spread = sum(abs(value - center) for value in ratios) / len(ratios)
    return 100.0 * spread / center


def weighted_mean_ratio(sales: list[dict]) -> float:
    total_assessed = sum(sale["assessed"] for sale in sales)
    total_price = sum(sale["price"] for sale in sales)
    if total_price <= 0:
        raise ValueError("the sale prices sum to zero")
    return total_assessed / total_price


def price_related_differential(sales: list[dict]) -> float:
    """Mean ratio over dollar-weighted mean ratio. Above 1.03 is regressive."""
    ratios = [ratio(sale["assessed"], sale["price"]) for sale in sales]
    mean_ratio = sum(ratios) / len(ratios)
    return mean_ratio / weighted_mean_ratio(sales)


def price_related_bias(sales: list[dict]) -> float:
    """Slope of ratio against value. Negative means cheaper homes carry more.

    The ratio is expressed as a share of the median and regressed on the
    base-two log of value, so the slope reads as the change in ratio each time
    a home's value doubles.
    """
    ratios = [ratio(sale["assessed"], sale["price"]) for sale in sales]
    center = median(ratios)
    if center == 0:
        raise ValueError("the median ratio is zero")
    points = []
    for sale, value in zip(sales, ratios):
        proxy = (sale["price"] * center + sale["assessed"]) / 2
        if proxy <= 0:
            continue
        points.append(((value - center) / center, math.log2(proxy)))
    if len(points) < 2:
        raise ValueError("a bias slope needs at least two sales")
    mean_x = sum(x for _, x in points) / len(points)
    mean_y = sum(y for y, _ in points) / len(points)
    covariance = sum((x - mean_x) * (y - mean_y) for y, x in points)
    variance = sum((x - mean_x) ** 2 for _, x in points)
    if variance == 0:
        raise ValueError("every sale has the same value")
    return covariance / variance


def deciles(sales: list[dict], groups: int = 10) -> list[dict]:
    """Median ratio inside each price band, cheapest band first."""
    ordered = sorted(sales, key=lambda sale: sale["price"])
    if len(ordered) < groups:
        raise ValueError("not enough sales to split into bands")
    size = len(ordered) / groups
    bands = []
    for index in range(groups):
        start = int(round(index * size))
        end = int(round((index + 1) * size))
        block = ordered[start:end]
        ratios = [ratio(sale["assessed"], sale["price"]) for sale in block]
        bands.append({
            "band": index + 1,
            "sales": len(block),
            "low_price": block[0]["price"],
            "high_price": block[-1]["price"],
            "median_ratio": round(median(ratios), 4),
        })
    return bands


def uniformity_verdict(cod: float) -> str:
    return "even" if cod <= COD_MAX else "uneven"


def regressivity_verdict(prd: float, prb: float) -> str:
    """Agreement between the two measures, so one noisy number cannot decide."""
    prd_regressive = prd > PRD_RANGE[1]
    prb_regressive = prb < PRB_RANGE[0]
    prd_progressive = prd < PRD_RANGE[0]
    prb_progressive = prb > PRB_RANGE[1]
    if prd_regressive and prb_regressive:
        return "regressive"
    if prd_progressive and prb_progressive:
        return "progressive"
    if prd_regressive or prb_regressive:
        return "leans regressive"
    if prd_progressive or prb_progressive:
        return "leans progressive"
    return "within standard"


def assessment_gap(assessed: float, price: float, county_median_ratio: float) -> dict:
    """What this home would be assessed at under the county's typical ratio."""
    implied = price * county_median_ratio
    difference = assessed - implied
    return {
        "ratio": round(ratio(assessed, price), 4),
        "implied_assessed": round(implied),
        "difference": round(difference),
        "percent": round(100.0 * difference / implied, 1) if implied else 0.0,
    }
