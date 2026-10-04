"""A spoken conversation about one assessment, grounded in the ratio study.

Gemini may only use the figures assembled here. It is not allowed to invent a
tax rate, a bill, a deadline, or legal advice, and it is told to say when a
question cannot be answered from the data rather than guess at it.
"""

from __future__ import annotations

import os

import requests

from api.fair import NEXT_REVALUATION, inherit, parcel
from api.settings import MODEL_URL, load_env

HISTORY_TURNS = 6
MAX_QUESTION = 400
MAX_TURN = 400

RULES = (
    "You are the voice of Fair Share, a tool that checks whether Wake County assessed a home fairly. "
    "Your answer is read aloud, so reply in one or two short spoken sentences, "
    "with no bullet points, no markdown, no headings, and no symbols other than dollar signs and percent signs. "
    "Do not recap facts the homeowner already heard unless they asked again.\n"
    "Use only the figures in the data block. Never introduce a number that is not there.\n"
    "Every selected home sold in the 2024 revaluation year, so its sale and the current assessment are from the same moment. "
    "A sales ratio is the county assessed value divided by the actual sale price. "
    "A ratio above the county median means the home is assessed more heavily relative to what it sold for.\n"
    "Never state or estimate a tax rate, a tax bill, a dollar amount of tax owed, or an appeal deadline, "
    "and never say the homeowner will win an appeal. A high ratio is evidence worth checking, not proof.\n"
    "If you are asked whether the county is fair, or anything else about the county overall, you must give "
    "both halves of the finding: that Wake meets all four published standards, and that the median ratio "
    "still declines steadily from the cheapest homes to the most expensive ones. Never report only one half, "
    "and do not call the county simply fair or simply unfair.\n"
    "If asked where a buyer could purchase, or what they would inherit, use the buying block. "
    "A buyer inherits the current assessed value until the next revaluation year listed there. "
    "Do not invent listings, mortgage rates, monthly payments, or future sale prices.\n"
    "If the question cannot be answered from the data block, say so in one sentence and then state the "
    "closest fact you do have. If the question is not about this home, this county's assessments, "
    "buying into an assessment, or how the study works, say that is outside what you can see and offer what you can answer."
)


def county_facts(model: dict) -> dict:
    county = model["county"]
    return {
        "county": "Wake County, North Carolina",
        "basis_year": county["basis_year"],
        "revaluation_date": county["revaluation"],
        "sales_analysed": county["sales"],
        "median_ratio": county["median_ratio"],
        "coefficient_of_dispersion": county["cod"],
        "price_related_differential": county["prd"],
        "price_related_bias": county["prb"],
        "uniformity_verdict": county["uniformity"],
        "regressivity_verdict": county["regressivity"],
        "iaao_standards": county["standards"],
        "median_ratio_by_price_band": [
            {
                "band": band["band"],
                "price_range": [band["low_price"], band["high_price"]],
                "median_ratio": band["median_ratio"],
                "sales": band["sales"],
            }
            for band in county["bands"]
        ],
        "note": (
            "Wake meets all four IAAO standards, and the price bands still decline from the cheapest "
            "homes to the most expensive ones. Both of those statements are true."
        ),
        "next_revaluation_year": NEXT_REVALUATION,
    }


def home_facts(detail: dict) -> dict:
    tract = detail["tract"]
    housing = tract.get("housing") or {}
    return {
        "address": detail["address"],
        "city": detail["city"],
        "sold_for": detail["price"],
        "assessed_at": detail["assessed"],
        "sale_date": detail["sale_date"],
        "sale_year": detail.get("sale_year"),
        "sale_and_assessment_are_same_year": detail.get("same_moment"),
        "year_built": detail["year_built"],
        "heated_square_feet": detail["heated_area"],
        "sales_ratio": detail["ratio"],
        "assessed_under_county_median_ratio": detail["versus_county"]["implied_assessed"],
        "dollars_above_county_norm": detail["versus_county"]["difference"],
        "percent_above_county_norm": detail["versus_county"]["percent"],
        "own_price_band": detail["band"],
        "dollars_above_own_price_band": (
            detail["versus_band"]["difference"] if detail["versus_band"] else None
        ),
        "cheapest_band_median_ratio": detail["cheapest_band_ratio"],
        "tract_name": tract["name"],
        "tract_median_ratio": tract["median_ratio"],
        "tract_coefficient_of_dispersion": tract.get("cod"),
        "tract_sales_analysed": tract.get("sales"),
        "tract_percent_from_county": tract.get("relative_to_county"),
        "tract_owner_occupied_share": housing.get("owner_share"),
        "tract_renter_cost_burdened_share": housing.get("renter_burden_share"),
        "tract_acs_median_owner_value": housing.get("median_home_value"),
    }


def build_facts(model: dict, pin: str | None) -> dict:
    facts = {
        "county_study": county_facts(model),
        "buying": {
            "meaning": (
                "A buyer inherits the house's current assessed value until the next "
                f"countywide revaluation in {NEXT_REVALUATION}. This is not a list of homes for sale."
            ),
            "at_350000": inherit(model, 350_000),
        },
    }
    if pin:
        facts["selected_home"] = home_facts(parcel(model, pin))
    else:
        facts["selected_home"] = None
        facts["no_home_note"] = "No home is selected, so answer about the county as a whole or about buying."
    return facts


def transcript(history: list[dict]) -> str:
    lines = []
    for turn in history[-HISTORY_TURNS:]:
        role = turn.get("role")
        text = turn.get("text")
        if role in {"you", "assistant"} and isinstance(text, str) and text.strip():
            speaker = "Homeowner" if role == "you" else "Fair Share"
            lines.append(f"{speaker}: {text.strip()[:MAX_TURN]}")
    return "\n".join(lines)


def fallback(model: dict, pin: str | None) -> str:
    county = model["county"]
    if not pin:
        return (
            f"Wake County's median ratio is {county['median_ratio']:.3f} and it meets all four IAAO standards, "
            "though cheaper homes still carry a higher ratio than expensive ones."
        )
    detail = parcel(model, pin)
    gap = detail["versus_county"]
    direction = "above" if gap["difference"] > 0 else "below"
    return (
        f"{detail['address']} sold for ${detail['price']:,.0f} and is assessed at "
        f"${detail['assessed']:,.0f}, a ratio of {detail['ratio']:.3f}. That is "
        f"${abs(gap['difference']):,.0f} {direction} the county norm of "
        f"{county['median_ratio']:.3f}."
    )


def _turns(history: list[dict], question: str) -> list[dict]:
    """Gemini's native conversation shape, so a follow-up can refer to the last answer."""
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
