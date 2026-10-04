"""House or Lot API. Wake County land vs building values, by address and tract.

Run from the repo root:

    .venv/bin/python api/server.py

GET /county
GET /search?q=johnsdale
GET /parcel?pin=0794369620
GET /tract?id=37183052505
GET /cities
GET /hotspots

POST /ask
POST /explain
POST /speak
"""

from __future__ import annotations

import json
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
from api.fair import cities, explain, hotspots, load_model, parcel, search, tract  # noqa: E402
from api.speech import synthesize  # noqa: E402

MODEL: dict = {}


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
    def _send(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_audio(self, audio: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)

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
            if parsed.path == "/appeal":
                self._send(200, {"ready": wallet_ready()})
                return
        except KeyError:
            self._send(404, {"error": "not found"})
            return
        except ValueError as error:
            self._send(400, {"error": str(error)})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in {"/explain", "/speak", "/appeal", "/ask"}:
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            if path == "/speak":
                text = str(payload.get("text", "")).strip()
                if not text:
                    raise ValueError("text is required")
                self._send_audio(synthesize(text[:800]))
                return
            if path == "/ask":
                history = payload.get("history")
                self._send(
                    200,
                    ask(
                        MODEL,
                        pin_from(payload),
                        str(payload.get("question", "")),
                        history if isinstance(history, list) else [],
                    ),
                )
                return
            pin = pin_from(payload)
            if not pin:
                raise ValueError("pin is required")
            if path == "/appeal":
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
                return
            self._send(200, explain(MODEL, pin))
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
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("House or Lot API at http://127.0.0.1:8000/county, /search, /parcel, /tract", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
