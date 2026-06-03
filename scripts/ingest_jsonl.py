"""Replay an events.jsonl log into SQLite (idempotent).

Demonstrates that events.jsonl is a replayable event log (same idea as a Kafka
topic / Redis stream, just a file). Safe to run repeatedly.

Usage:  python scripts/ingest_jsonl.py data/output/events.jsonl
"""
import os as _os, sys as _sys  # _PROJECT_ROOT_BOOTSTRAP
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


import json
import sys
from pathlib import Path

from backend.events import Event
from backend.store_sqlite import Store


def main(path: str) -> None:
    store = Store()
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ev = Event.model_validate_json(line)
            store.insert_event({
                "event_id": ev.event_id, "event_type": ev.event_type.value, "ts": ev.ts,
                "camera_id": ev.camera_id, "frame_idx": ev.frame_idx,
                "track_id": ev.track_id, "zone": ev.zone,
                "payload": json.dumps(ev.payload),
            })
            if ev.track_id is not None:
                store.upsert_track(ev.camera_id, ev.track_id, ev.ts, ev.zone,
                                   float(ev.payload.get("dwell_s", 0) or 0))
            if ev.is_alert:
                store.insert_alert({
                    "event_id": ev.event_id, "alert_type": ev.event_type.value, "ts": ev.ts,
                    "camera_id": ev.camera_id, "zone": ev.zone,
                    "severity": "critical" if ev.event_type.value == "afterhours_alert" else "warning",
                    "detail": json.dumps(ev.payload),
                })
            n += 1
    print(f"[ingest] replayed {n} events from {path} into data/store.db")


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "data/output/events.jsonl"
    if not Path(p).exists():
        print(f"file not found: {p}")
        sys.exit(1)
    main(p)
