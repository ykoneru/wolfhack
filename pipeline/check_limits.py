"""Check Ask rate limits without calling Gemini."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.limits import (  # noqa: E402
    DAILY_GEMINI_BUDGET,
    IP_ASK_LIMIT,
    IP_ASK_WINDOW,
    allow_ask,
    reset_limits,
    take_gemini_slot,
)


def main() -> None:
    reset_limits()
    start = 1_000_000.0
    for i in range(IP_ASK_LIMIT):
        allowed, retry = allow_ask("1.1.1.1", now=start + i)
        assert allowed, f"question {i + 1} should pass"
        assert retry == 0

    allowed, retry = allow_ask("1.1.1.1", now=start + IP_ASK_LIMIT)
    assert not allowed
    assert retry >= 1

    other, retry = allow_ask("8.8.8.8", now=start + IP_ASK_LIMIT)
    assert other and retry == 0

    later, retry = allow_ask("1.1.1.1", now=start + IP_ASK_WINDOW + 1)
    assert later and retry == 0

    reset_limits()
    for _ in range(DAILY_GEMINI_BUDGET):
        assert take_gemini_slot(day="2026-10-04")
    assert not take_gemini_slot(day="2026-10-04")
    assert take_gemini_slot(day="2026-10-05")

    print("limit checks passed")


if __name__ == "__main__":
    main()
