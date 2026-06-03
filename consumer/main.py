"""Stream consumer: Redis Streams -> PostgreSQL (+ anomaly detection).

Uses a consumer group so the work can be scaled horizontally and so unacked
messages are redelivered (at-least-once). Idempotent DB writes (ON CONFLICT
DO NOTHING on event_id) make replays safe.

Run:
    python -m consumer.main
"""
from __future__ import annotations

import json
import signal
import sys
import time

import redis

from backend.config import get_settings
from backend.db import Database
from backend.events import Event
from consumer.anomaly import AnomalyEngine

_RUNNING = True


def _stop(*_):  # graceful shutdown
    global _RUNNING
    _RUNNING = False


def ensure_group(r: redis.Redis, stream: str, group: str) -> None:
    try:
        r.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
        print(f"[consumer] created group '{group}' on '{stream}'")
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def persist(db: Database, event: Event) -> None:
    db.insert_event({
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "ts": event.ts,
        "camera_id": event.camera_id,
        "frame_idx": event.frame_idx,
        "track_id": event.track_id,
        "zone": event.zone,
        "payload": json.dumps(event.payload),
    })

    if event.track_id is not None:
        dwell = float(event.payload.get("dwell_s", 0) or 0)
        db.upsert_track(event.camera_id, event.track_id, event.ts,
                        event.zone, dwell_delta=dwell)

    if event.is_alert:
        db.insert_alert({
            "event_id": event.event_id,
            "alert_type": event.event_type.value,
            "ts": event.ts,
            "camera_id": event.camera_id,
            "zone": event.zone,
            "severity": "critical" if event.event_type.value == "afterhours_alert"
                        else "warning",
            "detail": json.dumps(event.payload),
        })


def main() -> int:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    s = get_settings()
    r = redis.Redis(host=s.redis_host, port=s.redis_port, decode_responses=True)
    db = Database()
    db.init_schema()
    ensure_group(r, s.redis_stream, s.redis_group)
    anomaly = AnomalyEngine(s)

    print(f"[consumer] '{s.redis_consumer}' listening on '{s.redis_stream}' ...")
    processed = 0
    while _RUNNING:
        try:
            resp = r.xreadgroup(
                groupname=s.redis_group, consumername=s.redis_consumer,
                streams={s.redis_stream: ">"}, count=100, block=2000,
            )
        except redis.ConnectionError:
            print("[consumer] redis connection lost, retrying ...")
            time.sleep(2)
            continue

        if not resp:
            continue

        for _stream, messages in resp:
            for msg_id, fields in messages:
                try:
                    event = Event.from_stream(fields)
                    persist(db, event)
                    for alert in anomaly.check(event):
                        persist(db, alert)            # store the derived alert too
                    processed += 1
                except Exception as exc:  # noqa: BLE001 - keep the consumer alive
                    print(f"[consumer] error on {msg_id}: {exc}")
                finally:
                    r.xack(s.redis_stream, s.redis_group, msg_id)

        if processed % 200 == 0:
            print(f"[consumer] processed={processed}", end="\r")

    print(f"\n[consumer] shutting down. processed={processed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
