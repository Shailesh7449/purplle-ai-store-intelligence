"""Vision pipeline (producer).

    video frames --(OpenCV)--> YOLOv8 detect + ByteTrack --> EventGenerator
              --> Redis Stream (store:events)

Run:
    python -m pipeline.run --source data/videos/store.mp4 --camera cam-01
    python -m pipeline.run --source 0                      # webcam
    python -m pipeline.run --source rtsp://cam.local/stream # live camera
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

import redis

from backend.config import get_settings
from backend.events import Event
from pipeline.event_logic import EventGenerator
from pipeline.zones import load_layout


def publish(r: redis.Redis, stream: str, event: Event) -> None:
    r.xadd(stream, event.to_stream_fields())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Store Intelligence vision pipeline")
    p.add_argument("--source", default="data/videos/store.mp4",
                   help="video path, webcam index, or RTSP URL")
    p.add_argument("--camera", default="cam-01", help="camera id stamped on events")
    p.add_argument("--show", action="store_true", help="display annotated frames")
    p.add_argument("--max-frames", type=int, default=0, help="stop after N frames (0=all)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    s = get_settings()

    # Imported lazily so the rest of the project (API, tests) doesn't need torch.
    from ultralytics import YOLO

    print(f"[pipeline] loading model {s.yolo_model} ...")
    model = YOLO(s.yolo_model)

    r = redis.Redis(host=s.redis_host, port=s.redis_port, decode_responses=True)
    layout = load_layout()
    gen = EventGenerator(camera_id=args.camera, layout=layout)

    # ByteTrack via Ultralytics built-in tracker; stream=True keeps memory bounded.
    source = int(args.source) if str(args.source).isdigit() else args.source
    results = model.track(
        source=source,
        classes=[s.person_class_id],
        conf=s.detect_conf,
        tracker="bytetrack.yaml",
        persist=True,
        stream=True,
        verbose=False,
    )

    frame_idx = 0
    last_tick = time.time()
    published = 0
    print(f"[pipeline] streaming events to '{s.redis_stream}' ...")

    for res in results:
        frame_idx += 1
        h, w = res.orig_shape  # (height, width)
        ts_epoch = datetime.now(timezone.utc).timestamp()

        detections: list[tuple[int, float, float, list[int], float]] = []
        if res.boxes is not None and res.boxes.id is not None:
            ids = res.boxes.id.int().tolist()
            xyxy = res.boxes.xyxy.tolist()
            confs = res.boxes.conf.tolist()
            for tid, (x1, y1, x2, y2), conf in zip(ids, xyxy, confs):
                cx = ((x1 + x2) / 2) / w
                cy = ((y1 + y2) / 2) / h
                detections.append(
                    (int(tid), cx, cy,
                     [int(x1), int(y1), int(x2), int(y2)], float(conf))
                )

        for ev in gen.process_frame(frame_idx, detections, ts_epoch):
            publish(r, s.redis_stream, ev)
            published += 1

        # ~1 occupancy snapshot per second
        if time.time() - last_tick >= 1.0:
            for ev in gen.occupancy_snapshot(frame_idx, ts_epoch):
                publish(r, s.redis_stream, ev)
                published += 1
            last_tick = time.time()
            print(f"[pipeline] frame={frame_idx} active_tracks={len(gen.tracks)} "
                  f"events_published={published}", end="\r")

        if args.max_frames and frame_idx >= args.max_frames:
            break

    print(f"\n[pipeline] done. frames={frame_idx} events_published={published}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
