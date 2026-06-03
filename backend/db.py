"""PostgreSQL access layer (psycopg 3).

A tiny connection-pool wrapper plus the SQL schema. We keep raw SQL (no ORM)
because the queries are simple, the analytics are aggregate-heavy, and it keeps
the data model transparent for reviewers.
"""
from __future__ import annotations

import signal
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

from backend.config import get_settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id           BIGSERIAL PRIMARY KEY,
    event_id     UUID UNIQUE NOT NULL,
    event_type   TEXT NOT NULL,
    ts           TIMESTAMPTZ NOT NULL,
    camera_id    TEXT NOT NULL,
    frame_idx    INTEGER NOT NULL DEFAULT 0,
    track_id     INTEGER,
    zone         TEXT,
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_ts        ON events (ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_type      ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_zone      ON events (zone);
CREATE INDEX IF NOT EXISTS idx_events_track     ON events (track_id);

-- Materialised-ish per-track lifecycle (kept current by the consumer)
CREATE TABLE IF NOT EXISTS tracks (
    track_id     INTEGER NOT NULL,
    camera_id    TEXT NOT NULL,
    first_seen   TIMESTAMPTZ NOT NULL,
    last_seen    TIMESTAMPTZ NOT NULL,
    last_zone    TEXT,
    total_dwell_s DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (camera_id, track_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id           BIGSERIAL PRIMARY KEY,
    event_id     UUID UNIQUE NOT NULL,
    alert_type   TEXT NOT NULL,
    ts           TIMESTAMPTZ NOT NULL,
    camera_id    TEXT NOT NULL,
    zone         TEXT,
    severity     TEXT NOT NULL DEFAULT 'warning',
    detail       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts DESC);
"""


class Database:
    def __init__(self, dsn: str | None = None, connect_timeout: int = 3) -> None:
        self.dsn = dsn or get_settings().pg_dsn
        self.connect_timeout = connect_timeout

    @contextmanager
    def conn(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=self.connect_timeout) as c:
            yield c

    def init_schema(self, suppress_errors: bool = True) -> bool:
        """Initialize schema with timeout. Returns True on success, False if DB unavailable.
        
        Args:
            suppress_errors: If True, log errors but don't raise. Used for non-blocking startup.
        """
        try:
            with self.conn() as c:
                c.execute(SCHEMA_SQL)
                c.commit()
            return True
        except Exception as e:  # noqa: BLE001
            if suppress_errors:
                print(f"[db] schema init failed (non-blocking): {e}")
                return False
            else:
                raise

    # --- writes (used by consumer) ---
    def insert_event(self, e: dict) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT INTO events
                    (event_id, event_type, ts, camera_id, frame_idx, track_id, zone, payload)
                VALUES
                    (%(event_id)s, %(event_type)s, %(ts)s, %(camera_id)s,
                     %(frame_idx)s, %(track_id)s, %(zone)s, %(payload)s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                e,
            )
            c.commit()

    def upsert_track(self, camera_id: str, track_id: int, ts: str,
                     zone: str | None, dwell_delta: float = 0.0) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT INTO tracks (track_id, camera_id, first_seen, last_seen, last_zone, total_dwell_s)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (camera_id, track_id) DO UPDATE
                  SET last_seen = EXCLUDED.last_seen,
                      last_zone = COALESCE(EXCLUDED.last_zone, tracks.last_zone),
                      total_dwell_s = tracks.total_dwell_s + EXCLUDED.total_dwell_s
                """,
                (track_id, camera_id, ts, ts, zone, dwell_delta),
            )
            c.commit()

    def insert_alert(self, a: dict) -> None:
        with self.conn() as c:
            c.execute(
                """
                INSERT INTO alerts (event_id, alert_type, ts, camera_id, zone, severity, detail)
                VALUES (%(event_id)s, %(alert_type)s, %(ts)s, %(camera_id)s,
                        %(zone)s, %(severity)s, %(detail)s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                a,
            )
            c.commit()
