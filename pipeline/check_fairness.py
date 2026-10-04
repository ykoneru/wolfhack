"""Check the ratio-study math against figures worked out by hand."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fairness import (  # noqa: E402
    assessment_gap,
    coefficient_of_dispersion,
    deciles,
    is_arms_length,
    median,
    price_related_bias,
    price_related_differential,
    ratio,
    regressivity_verdict,
    uniformity_verdict,
    weighted_mean_ratio,
)


def close(actual: float, expected: float, tolerance: float = 1e-6) -> bool:
    return abs(actual - expected) <= tolerance


def main() -> None:
    assert close(ratio(190_000, 200_000), 0.95)
    assert close(median([0.9, 1.0, 1.1]), 1.0)
    assert close(median([0.9, 1.0, 1.1, 1.2]), 1.05)

    # Ratios 0.8, 1.0, 1.2. Median 1.0, mean absolute spread 0.1333..., COD 13.33.
    even = [
        {"assessed": 80.0, "price": 100.0},
        {"assessed": 100.0, "price": 100.0},
        {"assessed": 120.0, "price": 100.0},
    ]
    assert close(coefficient_of_dispersion([0.8, 1.0, 1.2]), 100 * (0.4 / 3) / 1.0, 1e-9)
    assert uniformity_verdict(coefficient_of_dispersion([0.8, 1.0, 1.2])) == "even"
    assert uniformity_verdict(20.0) == "uneven"

    # Equal prices, so the dollar-weighted mean equals the plain mean and PRD is 1.
    assert close(weighted_mean_ratio(even), 1.0)
    assert close(price_related_differential(even), 1.0, 1e-9)

    # A cheap home assessed at 1.2 and an expensive one at 0.8 is regressive:
    # the plain mean stays 1.0 while the dollar-weighted mean drops below it.
    regressive = [
        {"assessed": 120_000.0, "price": 100_000.0},
        {"assessed": 800_000.0, "price": 1_000_000.0},
    ]
    prd = price_related_differential(regressive)
    assert prd > 1.03, prd
    prb = price_related_bias(regressive)
    assert prb < -0.05, prb
    assert regressivity_verdict(prd, prb) == "regressive"

    progressive = [
        {"assessed": 80_000.0, "price": 100_000.0},
        {"assessed": 1_200_000.0, "price": 1_000_000.0},
    ]
    assert regressivity_verdict(
        price_related_differential(progressive),
        price_related_bias(progressive),
    ) == "progressive"
    assert regressivity_verdict(1.0, 0.0) == "within standard"

    # A bundled deed and a house finished after the assessment are both dropped.
    assert is_arms_length({"assessed": 300_000, "price": 310_000, "year_built": 1998, "sale_year": 2024})
    assert not is_arms_length({"assessed": 367_170, "price": 2_790_500, "year_built": 2020, "sale_year": 2024})
    assert not is_arms_length({"assessed": 300_000, "price": 20_000, "year_built": 1998, "sale_year": 2024})
    assert not is_arms_length({"assessed": 400_000, "price": 400_500, "year_built": 2024, "sale_year": 2024})

    bands = deciles([
        {"assessed": float(price), "price": float(price)} for price in range(100_000, 120_000, 1_000)
    ])
    assert len(bands) == 10
    assert bands[0]["low_price"] == 100_000
    assert bands[-1]["high_price"] == 119_000
    assert all(close(band["median_ratio"], 1.0) for band in bands)

    gap = assessment_gap(assessed=420_000, price=400_000, county_median_ratio=0.95)
    assert gap["implied_assessed"] == 380_000
    assert gap["difference"] == 40_000
    assert close(gap["percent"], 10.5)

    print("fairness math checks passed")


if __name__ == "__main__":
    main()
