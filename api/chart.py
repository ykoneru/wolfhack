"""Hourly uncovered population for the closing-time chart.

Tiger Data stores the series. If that database is down or the URL is empty,
the same numbers come from hours.json.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from api.explain import load_env

ROOT = Path(__file__).resolve().parents[1]
HOURS_PATH = ROOT / "web" / "public" / "hours.json"
NEW_YORK = ZoneInfo("America/New_York")
SCENARIO_DAY = datetime(2026, 10, 2, tzinfo=NEW_YORK)


def hour_label(hour: int) -> str:
    clock = hour if hour <= 12 else hour - 12
    return f"{clock}{'am' if hour < 12 else 'pm'}"


def rows_from_file() -> list[dict]:
    document = json.loads(HOURS_PATH.read_text())
    rows = []
    for hour in document["hours"]:
        count = document["by_hour"][str(hour)]["uncovered_population"]
        rows.append({"hour": hour, "label": hour_label(hour), "uncovered_population": count})
    return rows


def database_url() -> str:
    """Read the saved connection string. An empty value already in the process does not stick."""
    url = ""
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("TIGER_DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not url:
        load_env()
        url = os.environ.get("TIGER_DATABASE_URL", "").strip()
    if not url or "sslmode=" in url:
        return url
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}sslmode=require"


def _ensure(connection, rows: list[dict]) -> None:
    try:
        connection.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    except Exception:
        pass
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS uncovered_hour (
            observed_at timestamptz PRIMARY KEY,
            hour smallint NOT NULL,
            uncovered_population integer NOT NULL
        )
        """
    )
    try:
        connection.execute(
            "SELECT create_hypertable('uncovered_hour', 'observed_at', if_not_exists => TRUE)"
        )
    except Exception:
        pass
    for row in rows:
        observed_at = SCENARIO_DAY.replace(hour=row["hour"])
        connection.execute(
            """
            INSERT INTO uncovered_hour (observed_at, hour, uncovered_population)
            VALUES (%s, %s, %s)
            ON CONFLICT (observed_at)
            DO UPDATE SET uncovered_population = EXCLUDED.uncovered_population
            """,
            (observed_at, row["hour"], row["uncovered_population"]),
        )
    try:
        connection.execute(
            """
            CREATE MATERIALIZED VIEW IF NOT EXISTS uncovered_hourly
            WITH (timescaledb.continuous) AS
            SELECT time_bucket('1 hour', observed_at) AS bucket,
                   max(uncovered_population) AS uncovered_population
            FROM uncovered_hour
            GROUP BY bucket
            WITH NO DATA
            """
        )
        connection.execute("CALL refresh_continuous_aggregate('uncovered_hourly', NULL, NULL)")
    except Exception:
        pass


def _query(connection) -> list[tuple]:
    try:
        fetched = connection.execute(
            """
            SELECT EXTRACT(HOUR FROM bucket AT TIME ZONE 'America/New_York')::int,
                   uncovered_population
            FROM uncovered_hourly
            ORDER BY bucket
            """
        ).fetchall()
        if fetched:
            return fetched
    except Exception:
        pass
    try:
        return connection.execute(
            """
            SELECT EXTRACT(HOUR FROM bucket AT TIME ZONE 'America/New_York')::int,
                   uncovered_population
            FROM (
                SELECT time_bucket('1 hour', observed_at) AS bucket,
                       max(uncovered_population) AS uncovered_population
                FROM uncovered_hour
                GROUP BY bucket
            ) hourly
            ORDER BY bucket
            """
        ).fetchall()
    except Exception:
        return connection.execute(
            """
            SELECT hour, uncovered_population
            FROM uncovered_hour
            ORDER BY hour
            """
        ).fetchall()


def rows_from_tiger(rows: list[dict]) -> list[dict]:
    import psycopg

    with psycopg.connect(database_url(), connect_timeout=8, autocommit=True) as connection:
        _ensure(connection, rows)
        fetched = _query(connection)
    return [
        {"hour": int(hour), "label": hour_label(int(hour)), "uncovered_population": int(count)}
        for hour, count in fetched
    ]


def chart() -> dict:
    rows = rows_from_file()
    url = database_url()
    if not url:
        return {"source": "hours.json", "hours": rows}
    try:
        stored = rows_from_tiger(rows)
    except Exception as error:
        message = str(error).replace(url, "TIGER_DATABASE_URL")
        print(f"tiger unavailable, using hours.json: {message}", flush=True)
        return {"source": "hours.json", "hours": rows}
    if not stored:
        return {"source": "hours.json", "hours": rows}
    return {"source": "tiger", "hours": stored}
