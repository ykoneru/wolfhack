"""Re-read the committed sample and confirm it still matches the scoring rules."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.rules import HOURS, burden  # noqa: E402


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    data = ROOT / "data" / "sample"
    web = ROOT / "web" / "public" / "sample"
    for name in ("tracts.geojson", "sites.geojson", "hours.json"):
        if load(data / name) != load(web / name):
            raise SystemExit(f"{name} differs between data/sample and web/public/sample")

    tracts = load(data / "tracts.geojson")["features"]
    sites = load(data / "sites.geojson")["features"]
    hours = load(data / "hours.json")

    if len(tracts) != 5 or len(sites) != 3:
        raise SystemExit("expected 5 tracts and 3 sites")

    for feature in tracts:
        props = feature["properties"]
        for hour in HOURS:
            stats = props["hourly"][str(hour)]
            expected = round(
                burden(
                    props["share_age_65_plus"],
                    props["poverty_rate"],
                    props["share_households_no_vehicle"],
                    stats["temperature_f"],
                    props["aqi"],
                ),
                4,
            )
            if stats["burden"] != expected:
                raise SystemExit(f"{props['id']} hour {hour} burden {stats['burden']} != {expected}")

    if hours["by_hour"]["14"]["uncovered_population"] != 0:
        raise SystemExit("2pm should cover every sample tract")
    if hours["by_hour"]["17"]["uncovered_population"] != 16400:
        raise SystemExit("5pm should uncover the four tracts away from the hospital")
    if hours["by_hour"]["17"]["tracts"]["sample-rex"]["covered"] is not True:
        raise SystemExit("the hospital tract should stay covered at 5pm")
    first = hours["by_hour"]["17"]["recommendations"]["1"]
    if not first or first[0]["site_id"] != "sample-south-library" or first[0]["people_added"] != 8400:
        raise SystemExit(f"unexpected first rescue pick: {first}")

    print("sample fixtures match the scoring rules")


if __name__ == "__main__":
    main()
