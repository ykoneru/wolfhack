"""Recommendations and explanations for FlowMap. Numbers come from activity.json."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from api.chart import database_url
from api.explain import MODEL_URL, load_env
from pipeline.flowmap import best_hour, category_for, clock_label

ROOT = Path(__file__).resolve().parents[1]
ACTIVITY_PATH = ROOT / "data" / "activity.json"
PLACES_PATH = ROOT / "data" / "places.json"
DAY = datetime(2026, 10, 3, tzinfo=ZoneInfo("America/New_York"))


def load_model() -> dict:
    activity = json.loads(ACTIVITY_PATH.read_text())
    places = json.loads(PLACES_PATH.read_text())["places"]
    by_id = {place["id"]: place for place in places}
    return {"activity": activity, "places": places, "by_id": by_id}


def _hours_label(place: dict) -> str:
    close = "midnight" if place["close"] >= 24 else clock_label(place["close"]).replace(":00", "")
    open_label = clock_label(place["open"]).replace(":00", "")
    prefix = "estimated " if place["hours_source"] == "default" else ""
    return f"{prefix}{open_label}–{close}"


def _because(current: dict, chosen: dict, place: dict) -> str:
    sentences = []
    if chosen["destinations"] < current["destinations"]:
        sentences.append("The destination score is lower then.")
    if chosen["commute"] < current["commute"]:
        sentences.append("The weekday commute score is lower then.")
    if place["hours_source"] == "default":
        sentences.append("The hours used here are the category default, not a confirmed schedule.")
    else:
        sentences.append("The place is still inside the hours recorded for it.")
    if abs(chosen["weather"] - current["weather"]) < 1:
        sentences.append("The weather adjustment barely changes.")
    return " ".join(sentences)


def recommend(model: dict, place_id: str, earliest: int, latest: int, minimum_minutes: int, current_hour: int) -> dict:
    place = model["by_id"].get(place_id)
    if place is None:
        raise KeyError(place_id)
    series = model["activity"]["tracts"][place["tract_id"]]
    if str(current_hour) not in series:
        raise ValueError("hour is outside 8am to 10pm")
    chosen = best_hour(series, place["open"], place["close"], earliest, latest, minimum_minutes)
    current = series[str(current_hour)]
    if chosen is None:
        return {
            "place_id": place["id"],
            "name": place["name"],
            "category": place["category"],
            "tract_id": place["tract_id"],
            "recommended_time": None,
            "reason": "No hour in that window leaves enough time before the place closes.",
            "current_score": current["score"],
            "current_category": current["category"],
        }
    best = series[str(chosen["hour"])]
    difference = round(current["score"] - best["score"], 1)
    reduction = 0 if current["score"] <= 0 else round(difference / current["score"] * 100)
    facts = {
        "place": place["name"],
        "place_category": place["category"],
        "hours": _hours_label(place),
        "hours_source": place["hours_source"],
        "current_time": clock_label(current_hour),
        "current_score": current["score"],
        "current_category": current["category"],
        "best_time": clock_label(chosen["hour"]),
        "best_score": best["score"],
        "best_category": best["category"],
        "reduction_percent": reduction,
        "population": current["population"],
        "roads": current["roads"],
        "commute_now": current["commute"],
        "commute_best": best["commute"],
        "destinations_now": current["destinations"],
        "destinations_best": best["destinations"],
        "weather_now": current["weather"],
        "weather_best": best["weather"],
    }
    explanation = (
        f"Estimated activity near {place['name']} is {best['score']} at {facts['best_time']}, "
        f"compared with {current['score']} at {facts['current_time']}. "
        f"{_because(current, best, place)}"
    )
    return {
        "place_id": place["id"],
        "name": place["name"],
        "category": place["category"],
        "tract_id": place["tract_id"],
        "current_hour": current_hour,
        "current_score": current["score"],
        "current_category": current["category"],
        "recommended_hour": chosen["hour"],
        "recommended_time": facts["best_time"],
        "score": best["score"],
        "activity_category": best["category"],
        "difference": difference,
        "estimated_reduction_percent": reduction,
        "hours": facts["hours"],
        "reason_codes": _codes(current, best, place),
        "factors_now": current,
        "factors_best": best,
        "explanation": explanation,
        "facts": facts,
    }


def _codes(current: dict, best: dict, place: dict) -> list[str]:
    codes = []
    if best["commute"] < current["commute"]:
        codes.append("commute_activity_decreasing")
    if best["destinations"] < current["destinations"]:
        codes.append("destination_score_decreasing")
    codes.append("destination_still_open")
    if abs(best["weather"] - current["weather"]) < 1:
        codes.append("weather_stable")
    if place["hours_source"] == "default":
        codes.append("hours_are_estimated")
    return codes


def explain(model: dict, place_id: str, earliest: int, latest: int, minimum_minutes: int, current_hour: int) -> dict:
    result = recommend(model, place_id, earliest, latest, minimum_minutes, current_hour)
    fallback = result.get("explanation") or result.get("reason")
    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or not result.get("facts"):
        return {"reply": fallback, "source": "fallback", "recommendation": result}
    prompt = (
        "Explain in two sentences why this is a better time to visit. "
        "Use only the facts below. Do not invent traffic, crowd counts, wait times, or facts not provided. "
        "A lower commute score means less estimated commuting activity, not a faster trip. "
        "If the destination score drops more than the commute score, say that the destination score is the larger change. "
        "This is an estimate, not a live crowd count.\n"
        f"Facts: {result['facts']}"
    )
    try:
        response = requests.post(
            MODEL_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        response.raise_for_status()
        reply = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError, TypeError):
        return {"reply": fallback, "source": "fallback", "recommendation": result}
    if not reply:
        return {"reply": fallback, "source": "fallback", "recommendation": result}
    return {"reply": reply, "source": "gemini", "recommendation": result}


def search_places(model: dict, query: str, limit: int = 8) -> list[dict]:
    text = query.strip().lower()
    if len(text) < 2:
        return []
    found = [place for place in model["places"] if place["named"] and text in place["name"].lower()]
    return found[:limit]


def series(model: dict, tract_id: str) -> dict:
    hours = model["activity"]["tracts"].get(tract_id)
    if hours is None:
        raise KeyError(tract_id)
    rows = [
        {"hour": int(hour), "label": clock_label(int(hour)), "score": block["score"], "category": block["category"]}
        for hour, block in hours.items()
    ]
    url = database_url()
    if not url:
        return {"source": "activity.json", "tract_id": tract_id, "hours": rows}
    try:
        _store(url, tract_id, rows)
    except Exception as error:
        print(f"tiger unavailable, using activity.json: {str(error).replace(url, 'TIGER_DATABASE_URL')}", flush=True)
        return {"source": "activity.json", "tract_id": tract_id, "hours": rows}
    return {"source": "tiger", "tract_id": tract_id, "hours": rows}


def _store(url: str, tract_id: str, rows: list[dict]) -> None:
    import psycopg

    with psycopg.connect(url, connect_timeout=8, autocommit=True) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_hour (
                tract_id text NOT NULL,
                observed_at timestamptz NOT NULL,
                hour smallint NOT NULL,
                score double precision NOT NULL,
                PRIMARY KEY (tract_id, observed_at)
            )
            """
        )
        for row in rows:
            connection.execute(
                """
                INSERT INTO activity_hour (tract_id, observed_at, hour, score)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tract_id, observed_at)
                DO UPDATE SET score = EXCLUDED.score
                """,
                (tract_id, DAY.replace(hour=row["hour"]), row["hour"], row["score"]),
            )


def category_for_score(score: float) -> str:
    return category_for(score)


def driving_route(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    """A driving route between two points. A straight line is the backup."""
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{from_lon},{from_lat};{to_lon},{to_lat}?overview=full&geometries=geojson"
    )
    try:
        response = requests.get(url, timeout=8, headers={"User-Agent": "flowmap wolfhack (ykoneru@ncsu.edu)"})
        response.raise_for_status()
        leg = response.json()["routes"][0]
        return {
            "minutes": max(1, round(leg["duration"] / 60)),
            "miles": round(leg["distance"] / 1609.344, 1),
            "geometry": leg["geometry"],
            "source": "road network",
        }
    except (requests.RequestException, KeyError, IndexError, TypeError):
        from pipeline.rules import haversine_miles

        miles = haversine_miles(from_lat, from_lon, to_lat, to_lon)
        return {
            "minutes": max(1, round(miles / 25 * 60)),
            "miles": round(miles, 1),
            "geometry": {"type": "LineString", "coordinates": [[from_lon, from_lat], [to_lon, to_lat]]},
            "source": "straight-line estimate",
        }
