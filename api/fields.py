"""Load scored Triangle fields and the facts a reply is allowed to use."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.rules import FIELD_LINE, HOURS

ROOT = Path(__file__).resolve().parents[1]
FIELDS_PATH = ROOT / "data" / "fields.json"


def load_document() -> dict:
    return json.loads(FIELDS_PATH.read_text())


def field_by_id(document: dict, field_id: str) -> dict:
    for field in document["fields"]:
        if field["id"] == field_id:
            return field
    raise KeyError(field_id)


def field_facts(field: dict, hour: int) -> dict:
    if hour not in HOURS:
        raise ValueError(f"hour must be one of {HOURS}")
    block = field["hourly"][str(hour)]
    over = [item["label"] for item in field["hourly"].values() if item["crossed"]]
    return {
        "field": field["name"],
        "sport": field["sport"],
        "land_cover": field["land_cover"],
        "time": block["label"],
        "forecast_f": block["forecast_f"],
        "ground_temperature_f": block["temperature_f"],
        "sky": block["sky"],
        "ground": block["ground"],
        "air": block["air"],
        "aqi": field["aqi"],
        "together": block["index"],
        "line": FIELD_LINE,
        "crossed": block["crossed"],
        "hours_over_the_line": over,
        "people_around": field["population_around"],
        "percent_age_65_plus": field["percent_age_65_plus"],
        "decision": "pause play" if block["crossed"] else "this field can stay open",
    }


def fallback_reply(facts: dict) -> str:
    decision = "Pause play." if facts["crossed"] else "This field can stay open."
    age = facts["percent_age_65_plus"]
    nearby = (
        f" About {facts['people_around']:,} people live in the surrounding tract"
        + (f", {age} percent of them 65 or older." if age is not None else ".")
    )
    return (
        f"At {facts['time']}, {facts['field']} is {facts['ground_temperature_f']} degrees on the ground "
        f"against a {facts['forecast_f']} degree forecast. "
        f"Sky is {facts['sky']}, pavement is {facts['ground']}, air is {facts['air']}, "
        f"and together they are {facts['together']} against a line of {facts['line']}. "
        f"{decision}{nearby}"
    )
