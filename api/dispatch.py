"""Speak the staffer sentence and reuse the audio when the buildings stay the same."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests

from api.explain import facts_for, fallback_paragraphs, load_env

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "raw" / "dispatch"
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
TTS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"


def cache_file(facts: dict) -> Path:
    names = "|".join(item["name"] for item in facts["buildings"])
    digest = hashlib.sha256(f"{facts['time']}|{names}".encode()).hexdigest()[:20]
    return CACHE / f"{digest}.mp3"


def synthesize(text: str) -> bytes:
    load_env()
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is empty")
    response = requests.post(
        TTS_URL,
        headers={"xi-api-key": api_key, "Accept": "audio/mpeg", "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_flash_v2_5"},
        timeout=60,
    )
    response.raise_for_status()
    return response.content


def dispatch(model: dict, hour: int, keep_open: list[str]) -> tuple[bytes, bool]:
    facts = facts_for(model, hour, keep_open)
    path = cache_file(facts)
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes(), True
    audio = synthesize(fallback_paragraphs(facts)["staffer"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return audio, False
