"""Seed the LITE SQLite DB with synthetic events — no YOLO/torch/video needed.

Lets you demo the API + dashboard instantly while the dataset/torch downloads.

Usage:  python scripts/seed_lite.py
Then:   uvicorn backend.main_lite:app   ->  http://localhost:8000
"""
import os as _os, sys as _sys  # _PROJECT_ROOT_BOOTSTRAP
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


import json
import random
from datetime import datetime, timedelta, timezone

from backend.store_sqlite import Store
from backend.events import EventType, make_event
from backend.config import get_settings
from consumer.anomaly import AnomalyEngine

ZONES = ["shelf_top", "foh", "shelf_bottom", "cash_counter"]


def _persist(store: Store, ev) -> None:
    store.insert_event({
        "event_id": ev.event_id, "event_type": ev.event_type.value, "ts": ev.ts,
        "camera_id": ev.camera_id, "frame_idx": ev.frame_idx, "track_id": ev.track_id,
        "zone": ev.zone, "payload": json.dumps(ev.payload),
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


def main(n_minutes: int = 30) -> None:
    store = Store()
    anomaly = AnomalyEngine(get_settings())
    cam = "cam-01"
    t0 = datetime.now(timezone.utc) - timedelta(minutes=n_minutes)
    tid = 0
    active: dict[int, tuple[str, datetime]] = {}
    total = 0

    for minute in range(n_minutes):
        for sec in range(0, 60, 3):
            now = t0 + timedelta(minutes=minute, seconds=sec)
            ts = now.isoformat()
            # arrivals
            if random.random() < 0.5:
                tid += 1
                zone = random.choices(ZONES, weights=[4, 5, 4, 2])[0]
                active[tid] = (zone, now)
                for et, extra in [
                    (EventType.track_started, {"payload": {"bbox": [0, 0, 50, 100], "conf": 0.82}}),
                    (EventType.zone_enter, {"zone": zone, "payload": {"bbox": [0, 0, 50, 100]}}),
                    (EventType.line_cross, {"zone": "door", "payload": {"direction": "in"}}),
                ]:
                    ev = make_event(et, cam, track_id=tid, ts=ts, **extra)
                    _persist(store, ev); total += 1
            # departures
            if active and random.random() < 0.4:
                leave = random.choice(list(active))
                zone, since = active.pop(leave)
                dwell = max(2, (now - since).total_seconds() + random.choice([0, 0, 90]))
                for et, extra in [
                    (EventType.zone_exit, {"zone": zone, "payload": {"dwell_s": round(dwell, 1)}}),
                    (EventType.line_cross, {"zone": "door", "payload": {"direction": "out"}}),
                ]:
                    ev = make_event(et, cam, track_id=leave, ts=ts, **extra)
                    _persist(store, ev); total += 1
                    for al in anomaly.check(ev):
                        _persist(store, al); total += 1
            # occupancy ticks (occasional crowd spike)
            for z in ZONES:
                base = sum(1 for (zz, _) in active.values() if zz == z)
                if random.random() < 0.03:
                    base += random.randint(6, 11)
                ev = make_event(EventType.occupancy_tick, cam, zone=z, ts=ts,
                                payload={"count": base})
                _persist(store, ev); total += 1
                for al in anomaly.check(ev):
                    _persist(store, al); total += 1

    print(f"[seed_lite] inserted {total} events into data/store.db")
    print("[seed_lite] now run:  uvicorn backend.main_lite:app   ->  http://localhost:8000")


if __name__ == "__main__":
    import sys
    if "--if-empty" in sys.argv:
        from backend.store_sqlite import Store as _S
        if _S().summary()["total_events"] > 0:
            print("[seed_lite] DB already has events; skipping (--if-empty).")
            raise SystemExit(0)
    main()
