"""Read-side analytics queries used by the API.

Separated from the write-side (db.py) to keep the CQRS-ish split clear:
the consumer writes facts, the API reads aggregates.
"""
from __future__ import annotations

from backend.db import Database


class Analytics:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()

    def summary(self) -> dict:
        with self.db.conn() as c:
            # current occupancy = latest occupancy_tick per zone, summed
            row = c.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (zone) zone,
                           (payload->>'count')::int AS count
                    FROM events
                    WHERE event_type = 'occupancy_tick'
                    ORDER BY zone, ts DESC
                )
                SELECT COALESCE(SUM(count), 0) AS occupancy FROM latest
                """
            ).fetchone()
            occupancy = row["occupancy"] if row else 0

            entries = c.execute(
                """SELECT COUNT(*) AS n FROM events
                   WHERE event_type='line_cross' AND payload->>'direction'='in'"""
            ).fetchone()["n"]

            exits = c.execute(
                """SELECT COUNT(*) AS n FROM events
                   WHERE event_type='line_cross' AND payload->>'direction'='out'"""
            ).fetchone()["n"]

            unique_visitors = c.execute(
                "SELECT COUNT(DISTINCT track_id) AS n FROM tracks"
            ).fetchone()["n"]

            active_alerts = c.execute(
                "SELECT COUNT(*) AS n FROM alerts WHERE ts > now() - interval '5 minutes'"
            ).fetchone()["n"]

            total_events = c.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]

        return {
            "current_occupancy": int(occupancy),
            "total_entries": int(entries),
            "total_exits": int(exits),
            "unique_visitors": int(unique_visitors),
            "active_alerts": int(active_alerts),
            "total_events": int(total_events),
        }

    def zones(self) -> list[dict]:
        with self.db.conn() as c:
            occ = c.execute(
                """
                SELECT DISTINCT ON (zone) zone, (payload->>'count')::int AS count
                FROM events WHERE event_type='occupancy_tick' AND zone IS NOT NULL
                ORDER BY zone, ts DESC
                """
            ).fetchall()
            dwell = c.execute(
                """
                SELECT zone,
                       ROUND(AVG((payload->>'dwell_s')::numeric), 1) AS avg_dwell_s,
                       COUNT(*) AS visits
                FROM events WHERE event_type='zone_exit' AND zone IS NOT NULL
                GROUP BY zone
                """
            ).fetchall()
        dmap = {d["zone"]: d for d in dwell}
        out = []
        for o in occ:
            d = dmap.get(o["zone"], {})
            out.append({
                "zone": o["zone"],
                "current_count": o["count"],
                "avg_dwell_s": float(d.get("avg_dwell_s") or 0),
                "visits": int(d.get("visits") or 0),
            })
        return out

    def recent_events(self, limit: int = 50, event_type: str | None = None,
                      zone: str | None = None) -> list[dict]:
        clauses, params = [], []
        if event_type:
            clauses.append("event_type = %s")
            params.append(event_type)
        if zone:
            clauses.append("zone = %s")
            params.append(zone)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self.db.conn() as c:
            rows = c.execute(
                f"""SELECT event_id, event_type, ts, camera_id, track_id, zone, payload
                    FROM events {where} ORDER BY ts DESC LIMIT %s""",
                params,
            ).fetchall()
        return rows

    def alerts(self, limit: int = 50) -> list[dict]:
        with self.db.conn() as c:
            return c.execute(
                """SELECT event_id, alert_type, ts, camera_id, zone, severity, detail
                   FROM alerts ORDER BY ts DESC LIMIT %s""",
                (limit,),
            ).fetchall()

    def footfall_timeseries(self, bucket_seconds: int = 60,
                            window_minutes: int = 60) -> list[dict]:
        with self.db.conn() as c:
            return c.execute(
                """
                SELECT to_char(date_bin(make_interval(secs => %s), ts, TIMESTAMPTZ 'epoch'),
                               'HH24:MI') AS bucket,
                       COUNT(*) FILTER (WHERE payload->>'direction'='in')  AS entries,
                       COUNT(*) FILTER (WHERE payload->>'direction'='out') AS exits
                FROM events
                WHERE event_type='line_cross'
                  AND ts > now() - make_interval(mins => %s)
                GROUP BY bucket ORDER BY bucket
                """,
                (bucket_seconds, window_minutes),
            ).fetchall()
