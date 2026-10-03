"""Recommend which buildings to keep open.

Run from the repo root:

    .venv/bin/python api/server.py

POST /recommend
{"hour": 18, "keep_open": ["osm-way-858326878"]}

hour is 14 through 20. keep_open is optional. The response is the new
uncovered population, the next buildings to keep open, and every tract.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, {})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/recommend":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            hour = int(payload.get("hour", 18))
            keep_open = payload.get("keep_open") or []
            if not isinstance(keep_open, list):
                raise ValueError("keep_open must be a list of site ids")
            self._send(200, build_response(hour, [str(site_id) for site_id in keep_open]))
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self._send(400, {"error": str(error)})

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} {format % args}", flush=True)


def main() -> None:
    load_model()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("recommend API at http://127.0.0.1:8000/recommend", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
