"""Download NC census tracts and join American Community Survey rates.

Writes data/tracts.geojson. Heat, air, and burden are added in later steps.
Raw downloads stay in data/raw, which is gitignored.
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path

import requests
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "tracts.geojson"
SHAPE_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_37_tract_500k.zip"
SHAPE_ZIP = RAW / "cb_2023_37_tract_500k.zip"
ACS_YEARS = (2024, 2023)
STATE_FIPS = "37"
MISSING = -999999999

AGE_65_PLUS = (
    "B01001_020E",
    "B01001_021E",
    "B01001_022E",
    "B01001_023E",
    "B01001_024E",
    "B01001_025E",
    "B01001_044E",
    "B01001_045E",
    "B01001_046E",
    "B01001_047E",
    "B01001_048E",
    "B01001_049E",
)
ACS_VARIABLES = (
    "NAME",
    "B01001_001E",
    *AGE_65_PLUS,
    "B17001_001E",
    "B17001_002E",
    "B08201_001E",
    "B08201_002E",
)


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        print(f"using cached {path.name}")
        return
    print(f"downloading {url}")
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    path.write_bytes(response.content)


def number(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    parsed = float(value)
    if parsed <= MISSING:
        return None
    return parsed


def round_coords(value, places: int = 5):
    if isinstance(value, list):
        if value and isinstance(value[0], (int, float)):
            return [round(float(item), places) for item in value]
        return [round_coords(item, places) for item in value]
    return value


def rate(part: float | None, whole: float | None) -> float | None:
    if part is None or whole is None or whole <= 0:
        return None
    return round(part / whole, 4)


def stats_row(values: dict[str, float | None], census_name: str | None) -> dict:
    population = values["B01001_001E"]
    age_65 = 0.0
    age_missing = False
    for column in AGE_65_PLUS:
        value = values[column]
        if value is None:
            age_missing = True
            break
        age_65 += value
    return {
        "census_name": census_name,
        "population": None if population is None else int(population),
        "share_age_65_plus": None if age_missing else rate(age_65, population),
        "poverty_rate": rate(values["B17001_002E"], values["B17001_001E"]),
        "share_households_no_vehicle": rate(values["B08201_002E"], values["B08201_001E"]),
    }


def fetch_acs_api(key: str) -> tuple[int, dict[str, dict]]:
    variables = ",".join(ACS_VARIABLES)
    last_error = None
    for year in ACS_YEARS:
        url = f"https://api.census.gov/data/{year}/acs/acs5"
        params = {"get": variables, "for": "tract:*", "in": f"state:{STATE_FIPS}", "key": key}
        print(f"requesting Census API ACS {year}")
        response = requests.get(url, params=params, timeout=120)
        if response.status_code != 200 or "application/json" not in response.headers.get("content-type", ""):
            last_error = f"ACS {year} returned {response.status_code}: {response.text[:200]}"
            continue
        rows = response.json()
        header, *records = rows
        table = {}
        for record in records:
            item = dict(zip(header, record))
            geoid = f"{item['state']}{item['county']}{item['tract']}"
            values = {column: number(item[column]) for column in ACS_VARIABLES if column != "NAME"}
            table[geoid] = stats_row(values, item["NAME"])
        return year, table
    raise SystemExit(last_error or "Census API request failed")


def fetch_acs_reporter() -> tuple[int, dict[str, dict]]:
    cache = RAW / "acs_nc.json"
    if cache.exists() and cache.stat().st_size > 0:
        print(f"using cached {cache.name}")
        payload = json.loads(cache.read_text())
    else:
        url = "https://api.censusreporter.org/1.0/data/show/latest?table_ids=B01001,B17001,B08201&geo_ids=140|04000US37"
        print("requesting Census Reporter ACS for North Carolina tracts")
        response = requests.get(
            url,
            headers={"User-Agent": "last-door wolfhack (ykoneru@ncsu.edu)"},
            timeout=180,
        )
        response.raise_for_status()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(response.content)
        payload = response.json()

    release = payload["release"]["id"]
    year = int(release.removeprefix("acs")[:4])
    table = {}
    for geo_id, tables in payload["data"].items():
        geoid = geo_id.removeprefix("14000US")
        values = {}
        for variable in ACS_VARIABLES:
            if variable == "NAME":
                continue
            table_id, line = variable.split("_")
            code = f"{table_id}{line.removesuffix('E')}"
            values[variable] = number(tables[table_id]["estimate"].get(code))
        table[geoid] = stats_row(values, None)
    return year, table


def fetch_acs() -> tuple[int, dict[str, dict]]:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if key:
        return fetch_acs_api(key)
    print("no CENSUS_API_KEY set, using Census Reporter for the same ACS tables")
    return fetch_acs_reporter()


def main() -> None:
    import geopandas as gpd

    load_env()
    download(SHAPE_URL, SHAPE_ZIP)
    with zipfile.ZipFile(SHAPE_ZIP) as archive:
        archive.extractall(RAW / "tracts")
    shapefile = next((RAW / "tracts").glob("*.shp"))
    tracts = gpd.read_file(shapefile)
    if tracts.crs is None:
        tracts = tracts.set_crs(4269)
    tracts = tracts.to_crs(4326)

    year, acs = fetch_acs()
    features = []
    matched = 0
    for row in tracts.itertuples(index=False):
        geoid = str(row.GEOID)
        stats = acs.get(geoid)
        if stats:
            matched += 1
        point = row.geometry.representative_point()
        properties = {
            "id": geoid,
            "name": row.NAMELSAD,
            "population": None if stats is None else stats["population"],
            "share_age_65_plus": None if stats is None else stats["share_age_65_plus"],
            "poverty_rate": None if stats is None else stats["poverty_rate"],
            "share_households_no_vehicle": None if stats is None else stats["share_households_no_vehicle"],
            "centroid": [round(point.x, 6), round(point.y, 6)],
            "acs_year": year,
        }
        features.append(
            {
                "type": "Feature",
                "geometry": round_coords(mapping(row.geometry)),
                "properties": properties,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}) + "\n")

    wake = [
        feature["properties"]
        for feature in features
        if feature["properties"]["id"].startswith("37183") and feature["properties"]["population"]
    ]
    wake.sort(key=lambda item: item["population"], reverse=True)
    example = wake[0]
    print(f"wrote {len(features)} tracts to {OUT.relative_to(ROOT)}")
    print(f"matched {matched} tracts to ACS {year}")
    print(
        f"example {example['id']} {example['name']}: "
        f"population {example['population']}, poverty rate {example['poverty_rate']}"
    )
    if len(features) < 2000:
        raise SystemExit("expected a little over 2,600 North Carolina tracts")


if __name__ == "__main__":
    main()
