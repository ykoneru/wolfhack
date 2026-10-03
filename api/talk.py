"""A short spoken reply about one field, using only that field's scores."""

from __future__ import annotations

import os

import requests

from api.explain import MODEL_URL, load_env
from api.fields import fallback_reply, field_facts


def talk(field: dict, hour: int, message: str, history: list[dict]) -> dict:
    facts = field_facts(field, hour)
    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"reply": fallback_reply(facts), "source": "fallback"}
    turns = []
    for item in history[-6:]:
        role = item.get("role")
        text = item.get("text")
        if role in {"user", "assistant"} and isinstance(text, str) and text.strip():
            turns.append(f"{role}: {text.strip()[:400]}")
    prompt = (
        "You are standing on one athletic field with the person who decides whether play continues. "
        "Use only the facts below. Sky is the forecast heat score, ground is the pavement score, "
        "and air is the air-quality score. Each of those can sit under the line while together crosses it. "
        "Say to pause play only when together is at or over the line. "
        "Do not invent a temperature, a count, a percent, a child count, a vehicle, a bus, or a building. "
        "If the question is outside these facts, say the scores do not include that. "
        "Reply in one or two sentences that can be read aloud.\n"
        f"Facts: {facts}\n"
        f"Conversation:\n" + "\n".join(turns) + f"\nuser: {message.strip()[:400]}"
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
        return {"reply": fallback_reply(facts), "source": "fallback"}
    if not reply:
        return {"reply": fallback_reply(facts), "source": "fallback"}
    return {"reply": reply, "source": "gemini"}
