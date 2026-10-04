"""Caps on Ask so a public API cannot empty a free Gemini key."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler

IP_ASK_LIMIT = 8
IP_ASK_WINDOW = 10 * 60
DAILY_GEMINI_BUDGET = 80
LIMITED_MESSAGE = "Ask is limited to 8 questions every 10 minutes. Try again shortly."

_lock = threading.Lock()
_asks: dict[str, deque[float]] = defaultdict(deque)
_gemini_day = ""
_gemini_used = 0


def reset_limits() -> None:
    global _gemini_day, _gemini_used
    with _lock:
        _asks.clear()
        _gemini_day = ""
        _gemini_used = 0


def client_ip(handler: BaseHTTPRequestHandler) -> str:
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        hop = forwarded.split(",", 1)[0].strip()
        if hop:
            return hop
    return handler.client_address[0]


def allow_ask(ip: str, now: float | None = None) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds). A denied call is not counted."""
    moment = time.time() if now is None else now
    with _lock:
        stamps = _asks[ip]
        cutoff = moment - IP_ASK_WINDOW
        while stamps and stamps[0] <= cutoff:
            stamps.popleft()
        if len(stamps) >= IP_ASK_LIMIT:
            retry = int(stamps[0] + IP_ASK_WINDOW - moment) + 1
            return False, max(retry, 1)
        stamps.append(moment)
        return True, 0


def take_gemini_slot(day: str | None = None) -> bool:
    """Reserve one Gemini call for the UTC day. False once the budget is gone."""
    global _gemini_day, _gemini_used
    today = day or time.strftime("%Y-%m-%d", time.gmtime())
    with _lock:
        if _gemini_day != today:
            _gemini_day = today
            _gemini_used = 0
        if _gemini_used >= DAILY_GEMINI_BUDGET:
            return False
        _gemini_used += 1
        return True
