"""FlowMap API. Estimated activity and a best time to go.

Run from the repo root:

    .venv/bin/python api/server.py

GET /activity?hour=17
GET /places?search=crabtree
GET /series?tract_id=37183052505
POST /recommend
{"place_id": "...", "earliest": 16, "latest": 21, "minimum_visit_minutes": 45, "hour": 17}

POST /explain
POST /speak
{"text": "Estimated activity is lower at 8:00 PM."}

POST /plan writes go:{place id}:{HHMM} on Solana devnet when the wallet is funded.
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
from api.dispatch import synthesize  # noqa: E402
from api.flow import driving_route, explain, load_model, recommend, search_places, series  # noqa: E402
from pipeline.flowmap import HOURS, clock_label  # noqa: E402

MODEL: dict = {}


def load() -> None:
    MODEL.clear()
    MODEL.update(load_model())
    print(f"loaded {len(MODEL['activity']['tracts'])} tracts and {len(MODEL['places'])} places", flush=True)


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
            if parsed.path == "/activity":
                hour = int(query.get("hour", ["17"])[0])
                if hour not in HOURS:
                    raise ValueError("hour is outside 8am to 10pm")
                scores = {
                    tract_id: {"score": block[str(hour)]["score"], "category": block[str(hour)]["category"]}
                    for tract_id, block in MODEL["activity"]["tracts"].items()
                }
                self._send(200, {"hour": hour, "label": clock_label(hour), "scores": scores})
                return
            if parsed.path == "/places":
                self._send(200, {"places": search_places(MODEL, query.get("search", [""])[0])})
                return
            if parsed.path == "/series":
                self._send(200, series(MODEL, query.get("tract_id", [""])[0]))
                return
            if parsed.path == "/plan":
                self._send(200, {"ready": wallet_ready()})
                return
            if parsed.path == "/route":
                self._send(
                    200,
                    driving_route(
                        float(query.get("from_lat", ["0"])[0]),
                        float(query.get("from_lon", ["0"])[0]),
                        float(query.get("to_lat", ["0"])[0]),
                        float(query.get("to_lon", ["0"])[0]),
                    ),
                )
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
        if path not in {"/recommend", "/explain", "/speak", "/plan"}:
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
            place_id = str(payload.get("place_id", "")).strip()
            if not place_id:
                raise ValueError("place_id is required")
            if path == "/plan":
                hour = int(payload.get("hour", 20))
                memo = f"go:{place_id}:{hour:02d}00"
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
            earliest = int(payload.get("earliest", 16))
            latest = int(payload.get("latest", 21))
            minimum = int(payload.get("minimum_visit_minutes", 45))
            hour = int(payload.get("hour", 17))
            if path == "/explain":
                self._send(200, explain(MODEL, place_id, earliest, latest, minimum, hour))
                return
            self._send(200, recommend(MODEL, place_id, earliest, latest, minimum, hour))
        except KeyError:
            self._send(404, {"error": "unknown place"})
        except (RuntimeError, requests.RequestException) as error:
            self._send(400, {"error": str(error)})
        except (ValueError, json.JSONDecodeError) as error:
            self._send(400, {"error": str(error)})

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} {format % args}", flush=True)


def main() -> None:
    load()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("FlowMap API at http://127.0.0.1:8000/activity, /places, /recommend, /explain, and /series", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
