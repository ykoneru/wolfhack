"""Speak an explanation with ElevenLabs, reusing the audio for repeated text."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests

from api.settings import load_env

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "raw" / "speech"
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
TTS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
# 1.0 is the default. 1.15 is noticeably quicker without sounding rushed.
SPEED = 1.15


def cache_file(text: str) -> Path:
    return CACHE / f"{hashlib.sha256(f'{SPEED}|{text}'.encode()).hexdigest()[:20]}.mp3"


def synthesize(text: str) -> bytes:
    path = cache_file(text)
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes()
    load_env()
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is empty")
    response = requests.post(
        TTS_URL,
        headers={"xi-api-key": api_key, "Accept": "audio/mpeg", "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": "eleven_flash_v2_5",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.7,
                "speed": SPEED,
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return response.content
