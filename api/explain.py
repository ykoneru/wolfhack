"""Two short paragraphs about the buildings to keep open.

Gemini may only repeat the facts we calculated. If the call fails, the same
facts are written out directly.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

from pipeline.rules import EXPOSED_BURDEN_MIN
from pipeline.score_hours import recommend, score_hour

ROOT = Path(__file__).resolve().parents[1]
MODEL_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


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


def hour_label(hour: int) -> str:
    clock = hour if 1 <= hour <= 12 else hour - 12
    return f"{clock}{'am' if hour < 12 else 'pm'}"


def percent(rate: float | None) -> int | None:
    if rate is None:
        return None
    return round(rate * 100)


def census_mix(model: dict, saved_ids: list[str]) -> dict:
    tracts = {props["id"]: props for props in model["tracts"]}
    chosen = [tracts[tract_id] for tract_id in saved_ids if tract_id in tracts]
    population = sum(props.get("population") or 0 for props in chosen)
    if population <= 0:
        return {"population": 0}
    def weighted(field: str) -> int | None:
        total = 0.0
        for props in chosen:
            value = props.get(field)
            if value is None:
                continue
            total += value * (props.get("population") or 0)
        return percent(total / population)
    return {
        "population": population,
        "percent_age_65_plus": weighted("share_age_65_plus"),
        "percent_in_poverty": weighted("poverty_rate"),
        "percent_households_without_a_vehicle": weighted("share_households_no_vehicle"),
    }


def saved_tracts(model: dict, hour: int, picks: list[dict], keep_open: set[str]) -> list[str]:
    scored = score_hour(model["tracts"], model["sites"], model["nearby"], hour, EXPOSED_BURDEN_MIN, keep_open)
    uncovered = {tract_id for tract_id, row in scored["tracts"].items() if row["uncovered"]}
    covers: dict[str, list[str]] = {}
    for props, pairs in zip(model["tracts"], model["nearby"]):
        for index, _distance in pairs:
            covers.setdefault(model["sites"][index]["id"], []).append(props["id"])
    saved: list[str] = []
    for pick in picks:
        for tract_id in covers.get(pick["site_id"], []):
            if tract_id in uncovered:
                saved.append(tract_id)
                uncovered.remove(tract_id)
    return saved


def facts_for(model: dict, hour: int, keep_open: list[str]) -> dict:
    known = model["names"]
    forced = {site_id for site_id in keep_open if site_id in known}
    scored = score_hour(model["tracts"], model["sites"], model["nearby"], hour, EXPOSED_BURDEN_MIN, forced)
    picks = recommend(model["tracts"], model["sites"], model["nearby"], hour, EXPOSED_BURDEN_MIN, forced)[:3]
    buildings = [
        {"name": known.get(pick["site_id"], pick["site_id"]), "people": pick["people_added"]}
        for pick in picks
    ]
    return {
        "time": hour_label(hour),
        "uncovered_people": scored["uncovered_population"],
        "buildings": buildings,
        "people_covered_by_these_buildings": sum(item["people"] for item in buildings),
        "census": census_mix(model, saved_tracts(model, hour, picks, forced)),
    }


def fallback_paragraphs(facts: dict) -> dict:
    names = [item["name"] for item in facts["buildings"]]
    covered = facts["people_covered_by_these_buildings"]
    listed = ", ".join(names[:-1]) + f", and {names[-1]}" if len(names) > 1 else (names[0] if names else "the nearest open public building")
    census = facts["census"]
    mix = ""
    if census.get("population"):
        mix = (
            f" Of the people those buildings cover, {census['percent_age_65_plus']} percent are 65 or older, "
            f"{census['percent_in_poverty']} percent live in poverty, and "
            f"{census['percent_households_without_a_vehicle']} percent of households have no vehicle."
        )
    return {
        "staffer": (
            f"At {facts['time']}, {facts['uncovered_people']} people have no open public building within 3 miles. "
            f"Keep {listed} open. Those buildings cover {covered} people.{mix}"
        ),
        "resident": (
            f"At {facts['time']}, the public buildings that still cover people are {listed}. "
            f"Together they are the closest open doors for {covered} people."
        ),
    }


def call_gemini(facts: dict) -> dict | None:
    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    prompt = (
        "Write two short paragraphs as JSON with keys staffer and resident. "
        "The staffer paragraph tells a city worker which buildings to keep open. "
        "The resident paragraph tells a person where they can go. "
        "Use only the facts below. Do not invent a building, a count, a percent, or a temperature.\n"
        f"{json.dumps(facts)}"
    )
    try:
        response = requests.post(
            MODEL_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError):
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    staffer = parsed.get("staffer")
    resident = parsed.get("resident")
    if not isinstance(staffer, str) or not isinstance(resident, str):
        return None
    return {"staffer": staffer.strip(), "resident": resident.strip()}


def explain(model: dict, hour: int, keep_open: list[str]) -> dict:
    facts = facts_for(model, hour, keep_open)
    generated = call_gemini(facts)
    if generated is None:
        paragraphs = fallback_paragraphs(facts)
        source = "fallback"
    else:
        paragraphs = generated
        source = "gemini"
    return {**paragraphs, "source": source, "facts": facts}
