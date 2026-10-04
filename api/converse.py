"""A spoken conversation about whether a buyer is purchasing a house or a lot."""

from __future__ import annotations

import os

import requests

from api.fair import hotspots, parcel
from api.settings import MODEL_URL, load_env

HISTORY_TURNS = 6
MAX_QUESTION = 400
MAX_TURN = 400

RULES = (
    "You are the voice of House or Lot, a tool that tells a Wake County buyer "
    "whether more of the county's value is the house or the land. "
    "Your answer is read aloud, so reply in one or two short spoken sentences, "
    "with no bullet points, no markdown, no headings, and no symbols other than dollar signs and percent signs. "
    "Do not recap facts the buyer already heard unless they asked again.\n"
    "Use only the figures in the data block. Never introduce a number that is not there.\n"
    "Land share is the county land value divided by land plus building. "
    "At or above 40 percent, the purchase is a lot. "
    "If it is also built in 1975 or earlier, it is teardown watch.\n"
    "Never state or estimate a tax rate, a tax bill, a mortgage, a list price, or a rebuild cost.\n"
    "If asked about the county overall, say the typical land share and that some neighborhoods "
    "are priced more as land while others are priced more as houses. Neither is good or bad. "
    "If asked where lots cluster, use the hotspots block.\n"
    "If the question cannot be answered from the data block, say so in one sentence and then state the "
    "closest fact you do have."
)


def county_facts(model: dict) -> dict:
    county = model["county"]
    return {
        "county": "Wake County, North Carolina",
        "homes": county["homes"],
        "median_land_share": county["median_land_share"],
        "house_count": county["house_count"],
        "lot_count": county["lot_count"],
        "teardown_count": county["teardown_count"],
        "lot_threshold": county.get("lot_threshold", 0.4),
        "teardown_year": county.get("teardown_year", 1975),
        "cities": county.get("cities", [])[:8],
        "note": (
            "A land share of 40 percent or more means the lot is the larger piece. "
            "That can be what a land buyer wants. An older house on that kind of lot is teardown watch."
        ),
    }


def home_facts(detail: dict) -> dict:
    tract = detail["tract"]
    return {
        "address": detail["address"],
        "city": detail["city"],
        "land_value": detail["land"],
        "building_value": detail["building"],
        "land_share": detail["land_share"],
        "verdict": detail["verdict_label"],
        "advice": detail["advice"],
        "year_built": detail["year_built"],
        "heated_square_feet": detail["heated_area"],
        "last_sale_price": detail.get("price"),
        "last_sale_date": detail.get("sale_date"),
        "versus_tract_percent": detail.get("versus_tract"),
        "tract_name": tract["name"],
        "tract_median_land_share": tract["median_land_share"],
        "tract_homes": tract.get("homes"),
        "tract_lot_count": tract.get("lot_count"),
        "tract_teardown_count": tract.get("teardown_count"),
    }


def build_facts(model: dict, pin: str | None) -> dict:
    facts = {
        "county_study": county_facts(model),
        "hotspots": hotspots(model),
    }
    if pin:
        facts["selected_home"] = home_facts(parcel(model, pin))
    else:
        facts["selected_home"] = None
        facts["no_home_note"] = "No home is selected, so answer about the county or about where lots cluster."
    return facts


def transcript(history: list[dict]) -> str:
    lines = []
    for turn in history[-HISTORY_TURNS:]:
        role = turn.get("role")
        text = turn.get("text")
        if role in {"you", "assistant"} and isinstance(text, str) and text.strip():
            speaker = "Buyer" if role == "you" else "House or Lot"
            lines.append(f"{speaker}: {text.strip()[:MAX_TURN]}")
    return "\n".join(lines)


def fallback(model: dict, pin: str | None) -> str:
    county = model["county"]
    if not pin:
        share = county["median_land_share"] * 100
        return (
            f"Wake County's typical land share is {share:.0f} percent. "
            f"{county['lot_count']:,} homes are priced as lots and "
            f"{county['teardown_count']:,} are teardown watch."
        )
    detail = parcel(model, pin)
    share = detail["land_share"] * 100
    return (
        f"{detail['address']} is a {detail['verdict_label'].lower()}. "
        f"Land is {share:.0f} percent of the split. {detail['advice']}"
    )


def _turns(history: list[dict], question: str) -> list[dict]:
    contents = []
    for turn in history[-HISTORY_TURNS:]:
        role = turn.get("role")
        text = turn.get("text")
        if role not in {"you", "assistant"} or not isinstance(text, str) or not text.strip():
            continue
        contents.append({
            "role": "user" if role == "you" else "model",
            "parts": [{"text": text.strip()[:MAX_TURN]}],
        })
    contents.append({"role": "user", "parts": [{"text": question}]})
    return contents


def ask(model: dict, pin: str | None, question: str, history: list[dict]) -> dict:
    text = question.strip()[:MAX_QUESTION]
    if not text:
        raise ValueError("question is required")
    spoken = fallback(model, pin)
    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"reply": spoken, "source": "fallback", "question": text}

    facts = build_facts(model, pin)
    try:
        response = requests.post(
            MODEL_URL,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "systemInstruction": {
                    "parts": [{"text": f"{RULES}\n\nData block:\n{facts}"}],
                },
                "contents": _turns(history, text),
            },
            timeout=30,
        )
        response.raise_for_status()
        reply = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError, TypeError) as error:
        print(f"gemini unavailable, using the written facts: {error}", flush=True)
        return {"reply": spoken, "source": "fallback", "question": text}
    if not reply:
        print("gemini returned nothing, using the written facts", flush=True)
        return {"reply": spoken, "source": "fallback", "question": text}
    return {"reply": reply, "source": "gemini", "question": text}
