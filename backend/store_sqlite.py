"""LITE-mode storage: SQLite via Python's stdlib `sqlite3` (zero install).

Replaces the Postgres layer for the disk-constrained build. Same logical schema,
same idempotency (INSERT OR IGNORE on event_id). Analytics use SQLite window
functions + json_extract, so no external DB process is required.

DB file defaults to data/store.db (gitignored).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB = Path("data/store.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT UNIQUE NOT NULL,
    event_type  TEXT NOT NULL,
    ts          TEXT NOT NULL,
    camera_id   TEXT NOT NULL,
    frame_idx   INTEGER NOT NULL DEFAULT 0,
    track_id    INTEGER,
    zone        TEXT,
    payload     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_ts   ON events (ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_zone ON events (zone);

CREATE TABLE IF NOT EXISTS tracks (
    track_id      INTEGER NOT NULL,
    camera_id     TEXT NOT NULL,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    last_zone     TEXT,
    total_dwell_s REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (camera_id, track_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT UNIQUE NOT NULL,
    alert_type  TEXT NOT NULL,
    ts          TEXT NOT NULL,
    camera_id   TEXT NOT NULL,
    zone        TEXT,
    severity    TEXT NOT NULL DEFAULT 'warning',
    detail      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts DESC);
"""


class Store:
    def __init__(self, db_path: str | Path = DEFAULT_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.db_path, timeout=30)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def init_schema(self) -> None:
        with self.conn() as c:
            c.executescript(SCHEMA_SQL)

    def clear_tables(self) -> None:
        with self.conn() as c:
            c.execute("DROP TABLE IF EXISTS events")
            c.execute("DROP TABLE IF EXISTS tracks")
            c.execute("DROP TABLE IF EXISTS alerts")
        self.init_schema()

    # ---------- writes ----------
    def insert_event(self, e: dict) -> None:
        with self.conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO events
                   (event_id,event_type,ts,camera_id,frame_idx,track_id,zone,payload)
                   VALUES (:event_id,:event_type,:ts,:camera_id,:frame_idx,:track_id,:zone,:payload)""",
                e,
            )

    def upsert_track(self, camera_id: str, track_id: int, ts: str,
                     zone: str | None, dwell_delta: float = 0.0) -> None:
        with self.conn() as c:
            c.execute(
                """INSERT INTO tracks (track_id,camera_id,first_seen,last_seen,last_zone,total_dwell_s)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(camera_id,track_id) DO UPDATE SET
                       last_seen=excluded.last_seen,
                       last_zone=COALESCE(excluded.last_zone, tracks.last_zone),
                       total_dwell_s=tracks.total_dwell_s + excluded.total_dwell_s""",
                (track_id, camera_id, ts, ts, zone, dwell_delta),
            )

    def insert_alert(self, a: dict) -> None:
        with self.conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO alerts
                   (event_id,alert_type,ts,camera_id,zone,severity,detail)
                   VALUES (:event_id,:alert_type,:ts,:camera_id,:zone,:severity,:detail)""",
                a,
            )

    # ---------- reads (analytics) ----------
    def summary(self) -> dict:
        with self.conn() as c:
            occ = c.execute(
                """WITH latest AS (
                       SELECT zone,
                              CAST(json_extract(payload,'$.count') AS INTEGER) AS count,
                              ROW_NUMBER() OVER (PARTITION BY zone ORDER BY ts DESC) rn
                       FROM events WHERE event_type='occupancy_tick' AND zone IS NOT NULL)
                   SELECT COALESCE(SUM(count),0) AS occ FROM latest WHERE rn=1"""
            ).fetchone()["occ"]
            entries = c.execute(
                "SELECT COUNT(*) n FROM events WHERE event_type='line_cross' "
                "AND json_extract(payload,'$.direction')='in'").fetchone()["n"]
            exits = c.execute(
                "SELECT COUNT(*) n FROM events WHERE event_type='line_cross' "
                "AND json_extract(payload,'$.direction')='out'").fetchone()["n"]
            visitors = c.execute("SELECT COUNT(*) n FROM tracks").fetchone()["n"]
            alerts = c.execute("SELECT COUNT(*) n FROM alerts").fetchone()["n"]
            total = c.execute("SELECT COUNT(*) n FROM events").fetchone()["n"]
        return {
            "current_occupancy": int(occ), "total_entries": int(entries),
            "total_exits": int(exits), "unique_visitors": int(visitors),
            "active_alerts": int(alerts), "total_events": int(total),
        }

    def zones(self) -> list[dict]:
        with self.conn() as c:
            occ = c.execute(
                """WITH latest AS (
                       SELECT zone,
                              CAST(json_extract(payload,'$.count') AS INTEGER) AS count,
                              ROW_NUMBER() OVER (PARTITION BY zone ORDER BY ts DESC) rn
                       FROM events WHERE event_type='occupancy_tick' AND zone IS NOT NULL)
                   SELECT zone, count FROM latest WHERE rn=1""").fetchall()
            dwell = c.execute(
                """SELECT zone,
                          ROUND(AVG(json_extract(payload,'$.dwell_s')),1) AS avg_dwell_s,
                          COUNT(*) AS visits
                   FROM events WHERE event_type='zone_exit' AND zone IS NOT NULL
                   GROUP BY zone""").fetchall()
        dmap = {d["zone"]: d for d in dwell}
        out = []
        for o in occ:
            d = dmap.get(o["zone"])
            out.append({
                "zone": o["zone"], "current_count": o["count"],
                "avg_dwell_s": float(d["avg_dwell_s"]) if d and d["avg_dwell_s"] else 0.0,
                "visits": int(d["visits"]) if d else 0,
            })
        return out

    def recent_events(self, limit=50, event_type=None, zone=None) -> list[dict]:
        clauses, params = [], []
        if event_type:
            clauses.append("event_type=?"); params.append(event_type)
        if zone:
            clauses.append("zone=?"); params.append(zone)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self.conn() as c:
            rows = c.execute(
                f"SELECT event_id,event_type,ts,camera_id,track_id,zone,payload "
                f"FROM events {where} ORDER BY ts DESC LIMIT ?", params).fetchall()
        return [self._row(r) for r in rows]

    def alerts(self, limit=50) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT event_id,alert_type,ts,camera_id,zone,severity,detail "
                "FROM alerts ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = json.loads(d["detail"]) if d["detail"] else {}
            out.append(d)
        return out

    def footfall_timeseries(self, window_minutes=60) -> list[dict]:
        # bucket by HH:MM (substr of ISO ts). Simple + SQLite-friendly.
        with self.conn() as c:
            rows = c.execute(
                """SELECT substr(ts,12,5) AS bucket,
                          SUM(CASE WHEN json_extract(payload,'$.direction')='in'  THEN 1 ELSE 0 END) AS entries,
                          SUM(CASE WHEN json_extract(payload,'$.direction')='out' THEN 1 ELSE 0 END) AS exits
                   FROM events WHERE event_type='line_cross'
                   GROUP BY bucket ORDER BY bucket""").fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _row(r: sqlite3.Row) -> dict:
        d = dict(r)
        if "payload" in d:
            d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
        return d
