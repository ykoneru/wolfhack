"""A typed conversation about whether a buyer is purchasing a house or a lot."""

from __future__ import annotations

import os

import requests

from api.fair import hotspots, parcel
from api.limits import take_gemini_slot
from api.settings import MODEL_URL, load_env

HISTORY_TURNS = 6
MAX_QUESTION = 400
MAX_TURN = 400

RULES = (
    "You are Parcel, a tool that tells a Wake County buyer "
    "whether more of the county's value is the house or the land. "
    "Reply in one or two short sentences, "
    "with no bullet points, no markdown, no headings, and no symbols other than dollar signs and percent signs. "
    "Do not recap facts the buyer already heard unless they asked again.\n"
    "Use only the figures in the data block. Never introduce a number that is not there.\n"
    "Land share is the county land value divided by land plus building. "
    "At or above 40 percent, the purchase is a lot. "
    "If it is also built in 1975 or earlier, it is teardown watch.\n"
    "Never state or estimate a tax rate, a tax bill, a mortgage, or a rebuild cost.\n"
    "If listing_price is in the data, you may say it is the RentCast list price, not the assessed value. "
    "If listing_price is missing, do not invent a list price.\n"
    "If asked about the county overall, say the typical land share and that some neighborhoods "
    "are priced more as land while others are priced more as houses. Neither is good or bad. "
    "If asked where lots cluster, use the hotspots block.\n"
    "If a comparison block is present, answer about those two sides and do not ignore one of them.\n"
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
        "listing_price": (detail.get("listing") or {}).get("price"),
        "listing_source": "RentCast" if detail.get("listing") else None,
    }


def subject_facts(model: dict, subject: dict | None) -> dict | None:
    if not isinstance(subject, dict):
        return None
    kind = subject.get("kind")
    if kind == "home" and subject.get("pin"):
        try:
            return {"kind": "home", **home_facts(parcel(model, str(subject["pin"])))}
        except KeyError:
            return None
    if kind == "neighborhood" and subject.get("id"):
        row = model["tracts"].get(str(subject["id"]))
        if row is None:
            return None
        return {
            "kind": "neighborhood",
            "name": row.get("name"),
            "median_land_share": row.get("median_land_share"),
            "median_land": row.get("median_land"),
            "median_building": row.get("median_building"),
            "homes": row.get("homes"),
            "lot_count": row.get("lot_count"),
            "teardown_count": row.get("teardown_count"),
        }
    if kind == "county":
        county = model["county"]
        return {
            "kind": "county",
            "name": "Wake County typical",
            "median_land_share": county["median_land_share"],
            "median_land": county.get("median_land"),
            "median_building": county.get("median_building"),
        }
    return None


def build_facts(model: dict, pin: str | None, compare: dict | None = None) -> dict:
    facts = {
        "county_study": county_facts(model),
        "hotspots": hotspots(model),
    }
    if isinstance(compare, dict) and (compare.get("left") or compare.get("right")):
        facts["comparison"] = {
            "first": subject_facts(model, compare.get("left")),
            "second": subject_facts(model, compare.get("right")),
            "note": "Answer about these two sides. The Compare panel gap is first minus second.",
        }
    if pin:
        facts["selected_home"] = home_facts(parcel(model, pin))
    else:
        facts["selected_home"] = None
        if "comparison" not in facts:
            facts["no_home_note"] = "No home is selected, so answer about the county or about where lots cluster."
    return facts


def transcript(history: list[dict]) -> str:
    lines = []
    for turn in history[-HISTORY_TURNS:]:
        role = turn.get("role")
        text = turn.get("text")
        if role in {"you", "assistant"} and isinstance(text, str) and text.strip():
            speaker = "Buyer" if role == "you" else "Parcel"
            lines.append(f"{speaker}: {text.strip()[:MAX_TURN]}")
    return "\n".join(lines)


def _share_label(row: dict | None) -> tuple[str, float] | None:
    if not row or row.get("land_share") is None and row.get("median_land_share") is None:
        return None
    share = row.get("land_share")
    if share is None:
        share = row.get("median_land_share")
    name = row.get("address") or row.get("name") or "this side"
    return name, float(share)


def fallback(model: dict, pin: str | None, compare: dict | None = None) -> str:
    if isinstance(compare, dict):
        left = _share_label(subject_facts(model, compare.get("left")))
        right = _share_label(subject_facts(model, compare.get("right")))
        if left and right:
            return (
                f"{left[0]} is {left[1] * 100:.0f} percent land. "
                f"{right[0]} is {right[1] * 100:.0f} percent land."
            )
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


def ask(model: dict, pin: str | None, question: str, history: list[dict], compare: dict | None = None) -> dict:
    text = question.strip()[:MAX_QUESTION]
    if not text:
        raise ValueError("question is required")
    spoken = fallback(model, pin, compare)
    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or not take_gemini_slot():
        return {"reply": spoken, "source": "fallback", "question": text}

    facts = build_facts(model, pin, compare)
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
