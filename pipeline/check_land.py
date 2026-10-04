"""Check the house-or-lot labels against figures worked out by hand."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.address import address_matches, canonical_address
from pipeline.land import advice, classify, land_share, median, verdict_label


def main() -> None:
    assert round(land_share(30_000, 70_000), 4) == 0.3
    assert round(land_share(50_000, 50_000), 4) == 0.5
    assert classify(0.27, 1998) == "house"
    assert classify(0.45, 2005) == "lot"
    assert classify(0.45, 1968) == "teardown"
    assert classify(0.45, None) == "lot"
    assert verdict_label("teardown") == "Teardown watch"
    assert "lot is the larger piece" in advice("lot").lower()
    assert "house is the larger piece" in advice("house").lower()
    assert "if you want the land" in advice("teardown").lower()
    assert median([0.2, 0.3, 0.4]) == 0.3
    assert canonical_address("724 TOULOUSE CT") == "724 toulouse court"
    assert address_matches("724 Toulouse Ct", "724 TOULOUSE COURT", "CARY")
    print("land checks passed")


if __name__ == "__main__":
    main()
