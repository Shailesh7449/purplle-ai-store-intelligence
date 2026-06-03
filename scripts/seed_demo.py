"""Publish synthetic events straight to Redis to demo the dashboard end-to-end
WITHOUT running YOLO/torch. Great for a quick UI demo or CI smoke test.

Usage: python scripts/seed_demo.py
Then start the consumer + API to see data flow through the real pipeline path.
"""
import os as _os, sys as _sys  # _PROJECT_ROOT_BOOTSTRAP
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


import random
import time

import redis

from backend.config import get_settings
from backend.events import EventType, make_event

ZONES = ["entrance", "aisle", "checkout"]


def main() -> None:
    s = get_settings()
    r = redis.Redis(host=s.redis_host, port=s.redis_port, decode_responses=True)
    cam = "cam-01"
    next_track = 1
    active: dict[int, str] = {}
    frame = 0
    print(f"[seed] publishing demo events to '{s.redis_stream}' (Ctrl-C to stop)")
    try:
        while True:
            frame += 1
            # spawn new visitor
            if random.random() < 0.4:
                tid = next_track; next_track += 1
                zone = random.choice(ZONES)
                active[tid] = zone
                r.xadd(s.redis_stream, make_event(
                    EventType.track_started, cam, frame_idx=frame, track_id=tid,
                    payload={"bbox": [0, 0, 50, 100], "conf": 0.8}).to_stream_fields())
                r.xadd(s.redis_stream, make_event(
                    EventType.zone_enter, cam, frame_idx=frame, track_id=tid,
                    zone=zone, payload={"bbox": [0, 0, 50, 100]}).to_stream_fields())
                r.xadd(s.redis_stream, make_event(
                    EventType.line_cross, cam, frame_idx=frame, track_id=tid,
                    zone="door", payload={"direction": "in"}).to_stream_fields())
            # someone leaves a zone (maybe long dwell -> alert)
            if active and random.random() < 0.3:
                tid = random.choice(list(active))
                zone = active.pop(tid)
                dwell = random.choice([8, 20, 45, 130, 160])  # some exceed threshold
                r.xadd(s.redis_stream, make_event(
                    EventType.zone_exit, cam, frame_idx=frame, track_id=tid,
                    zone=zone, payload={"dwell_s": dwell}).to_stream_fields())
                r.xadd(s.redis_stream, make_event(
                    EventType.line_cross, cam, frame_idx=frame, track_id=tid,
                    zone="door", payload={"direction": "out"}).to_stream_fields())
            # occupancy ticks (occasionally spike to trigger crowd alert)
            for z in ZONES:
                base = sum(1 for v in active.values() if v == z)
                if random.random() < 0.05:
                    base += random.randint(6, 12)  # spike
                r.xadd(s.redis_stream, make_event(
                    EventType.occupancy_tick, cam, frame_idx=frame, zone=z,
                    payload={"count": base}).to_stream_fields())
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[seed] stopped.")


if __name__ == "__main__":
    main()
