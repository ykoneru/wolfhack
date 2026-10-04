"""Parcel API. Wake County land vs building values, by address and tract.

Run from the repo root:

    .venv/bin/python api/server.py

GET /county
GET /search?q=johnsdale
GET /parcel?pin=0794369620
GET /tract?id=37183052505
GET /cities
GET /hotspots
GET /listings
GET /discover

POST /ask
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.commit import send_memo, wallet_ready  # noqa: E402
from api.converse import ask  # noqa: E402
from api.fair import cities, discover_homes, hotspots, listings, load_model, parcel, search, tract  # noqa: E402
from api.limits import LIMITED_MESSAGE, allow_ask, client_ip  # noqa: E402

MODEL: dict = {}
ALLOWED_ORIGINS = {
    "https://buyparcel.vip",
    "https://www.buyparcel.vip",
    "http://buyparcel.vip",
    "http://www.buyparcel.vip",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
}


def pin_from(payload: dict) -> str | None:
    value = payload.get("pin")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load() -> None:
    MODEL.clear()
    MODEL.update(load_model())
    graded = sum(1 for row in MODEL["tracts"].values() if row.get("enough_homes"))
    print(
        f"loaded {len(MODEL['homes'])} homes across {len(MODEL['tracts'])} tracts, "
        f"{graded} with enough homes to grade",
        flush=True,
    )


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict | list, extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        origin = self.headers.get("Origin", "")
        allowed = origin if origin in ALLOWED_ORIGINS else "https://buyparcel.vip"
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", allowed)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, {})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/county":
                self._send(200, MODEL["county"])
                return
            if parsed.path == "/search":
                self._send(200, {"matches": search(MODEL, query.get("q", [""])[0])})
                return
            if parsed.path == "/parcel":
                self._send(200, parcel(MODEL, query.get("pin", [""])[0]))
                return
            if parsed.path == "/tract":
                self._send(200, tract(MODEL, query.get("id", [""])[0]))
                return
            if parsed.path == "/cities":
                self._send(200, cities(MODEL))
                return
            if parsed.path == "/hotspots":
                self._send(200, hotspots(MODEL))
                return
            if parsed.path == "/listings":
                self._send(200, listings(MODEL))
                return
            if parsed.path == "/discover":
                self._send(200, discover_homes(MODEL))
                return
            if parsed.path == "/appeal":
                self._send(200, {"ready": wallet_ready()})
                return
        except KeyError:
            self._send(404, {"error": "not found"})
            return
        except requests.RequestException as error:
            self._send(503, {"error": str(error)})
            return
        except ValueError as error:
            self._send(400, {"error": str(error)})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in {"/appeal", "/ask"}:
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            if path == "/ask":
                allowed, retry_after = allow_ask(client_ip(self))
                if not allowed:
                    self._send(
                        429,
                        {"error": LIMITED_MESSAGE},
                        extra_headers={"Retry-After": str(retry_after)},
                    )
                    return
                history = payload.get("history")
                self._send(
                    200,
                    ask(
                        MODEL,
                        pin_from(payload),
                        str(payload.get("question", "")),
                        history if isinstance(history, list) else [],
                        payload.get("compare") if isinstance(payload.get("compare"), dict) else None,
                    ),
                )
                return
            pin = pin_from(payload)
            if not pin:
                raise ValueError("pin is required")
            detail = parcel(MODEL, pin)
            memo = f"lot:{pin}:{detail['land_share']:.3f}"
            signature = send_memo(memo)
            self._send(
                200,
                {
                    "memo": memo,
                    "signature": signature,
                    "explorer_url": f"https://explorer.solana.com/tx/{signature}?cluster=devnet",
                },
            )
        except KeyError:
            self._send(404, {"error": "unknown parcel"})
        except (RuntimeError, requests.RequestException) as error:
            self._send(400, {"error": str(error)})
        except (ValueError, json.JSONDecodeError) as error:
            self._send(400, {"error": str(error)})

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} {format % args}", flush=True)


def main() -> None:
    load()
    port = int(os.environ.get("PORT", "8000"))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Parcel API at http://{host}:{port}/county, /search, /parcel, /tract", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
