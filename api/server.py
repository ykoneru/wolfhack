"""Recommend which buildings to keep open.

Run from the repo root:

    .venv/bin/python api/server.py

POST /recommend
{"hour": 18, "keep_open": ["osm-way-858326878"]}

POST /explain
{"hour": 18, "keep_open": []}

POST /dispatch
{"hour": 18, "keep_open": []}

GET /chart

hour is 14 through 20. keep_open is optional.
/dispatch returns audio. A second request with the same buildings reads the saved file.
/chart returns uncovered population by hour. It reads Tiger Data, then hours.json.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.chart import chart  # noqa: E402
from api.dispatch import dispatch  # noqa: E402
from api.explain import explain  # noqa: E402
from pipeline.rules import EXPOSED_BURDEN_MIN, HOURS  # noqa: E402
from pipeline.score_hours import load_features, prepare, recommend, score_hour  # noqa: E402

TRACTS_PATH = ROOT / "data" / "tracts.geojson"
SITES_PATH = ROOT / "data" / "sites.geojson"
MODEL: dict = {}


def load_model() -> None:
    tracts, sites, nearby = prepare(load_features(TRACTS_PATH), load_features(SITES_PATH))
    MODEL["tracts"] = tracts
    MODEL["sites"] = sites
    MODEL["nearby"] = nearby
    MODEL["names"] = {site["id"]: site["name"] for site in sites}
    print(f"loaded {len(tracts)} tracts and {len(sites)} sites", flush=True)


def build_response(hour: int, keep_open: list[str]) -> dict:
    if hour not in HOURS:
        raise ValueError(f"hour must be one of {HOURS}")
    known = MODEL["names"]
    forced = {site_id for site_id in keep_open if site_id in known}
    scored = score_hour(MODEL["tracts"], MODEL["sites"], MODEL["nearby"], hour, EXPOSED_BURDEN_MIN, forced)
    picks = recommend(MODEL["tracts"], MODEL["sites"], MODEL["nearby"], hour, EXPOSED_BURDEN_MIN, forced)
    for pick in picks:
        pick["name"] = known.get(pick["site_id"], pick["site_id"])
    return {
        "hour": hour,
        "keep_open": sorted(forced),
        "uncovered_population": scored["uncovered_population"],
        "recommendations": {"1": picks[:1], "3": picks[:3], "5": picks[:5]},
        "tracts": scored["tracts"],
    }


def explain_response(hour: int, keep_open: list[str]) -> dict:
    if hour not in HOURS:
        raise ValueError(f"hour must be one of {HOURS}")
    return explain(MODEL, hour, keep_open)


def dispatch_response(hour: int, keep_open: list[str]) -> tuple[bytes, bool]:
    if hour not in HOURS:
        raise ValueError(f"hour must be one of {HOURS}")
    return dispatch(MODEL, hour, keep_open)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_audio(self, audio: bytes, cached: bool) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Cache", "hit" if cached else "miss")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, {})

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/chart":
            self._send(404, {"error": "not found"})
            return
        self._send(200, chart())

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in {"/recommend", "/explain", "/dispatch"}:
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            hour = int(payload.get("hour", 18))
            keep_open = payload.get("keep_open") or []
            if not isinstance(keep_open, list):
                raise ValueError("keep_open must be a list of site ids")
            keep_open = [str(site_id) for site_id in keep_open]
            if path == "/explain":
                self._send(200, explain_response(hour, keep_open))
            elif path == "/dispatch":
                audio, cached = dispatch_response(hour, keep_open)
                self._send_audio(audio, cached)
            else:
                self._send(200, build_response(hour, keep_open))
        except (RuntimeError, requests.RequestException) as error:
            self._send(400, {"error": str(error)})
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self._send(400, {"error": str(error)})

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} {format % args}", flush=True)


def main() -> None:
    load_model()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("API at http://127.0.0.1:8000/recommend, /explain, /dispatch, and /chart", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
