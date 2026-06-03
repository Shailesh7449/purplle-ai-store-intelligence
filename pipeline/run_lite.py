"""LITE pipeline — one process, no Redis/Postgres/Docker.

    video --> YOLOv8 + ByteTrack --> events --> events.jsonl (event log)
                                         |
                                         +--> SQLite (events/tracks/alerts)
                                         +--> anomaly checks

This is the disk- and time-friendly path. The event log (events.jsonl) IS your
replayable stream — same idea as Redis/Kafka, just a file. You can re-ingest it
later with scripts/ingest_jsonl.py.

Run:
    python -m pipeline.run_lite --source data/videos/store.mp4 --camera cam-01
    python -m pipeline.run_lite --source 0                 # webcam
    python -m pipeline.run_lite --source data/videos/store.mp4 --no-yolo  # replay logic only
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import os

if sys.platform == 'win32':
    try:
        os.add_dll_directory(str(Path(__file__).resolve().parent.parent))
    except AttributeError:
        pass

from backend.config import get_settings
from backend.store_sqlite import Store
from consumer.anomaly import AnomalyEngine
from pipeline.event_logic import EventGenerator
from pipeline.zones import load_layout
import cv2

JSONL_PATH = Path("data/output/events.jsonl")
_run_progress = {"processed_frames": 0, "total_frames": 0, "running": False}


def persist(store: Store, anomaly: AnomalyEngine, jsonl, event) -> int:
    """Write event to jsonl + sqlite, run anomaly, persist any alerts. Returns #written."""
    import json
    jsonl.write(event.model_dump_json() + "\n")
    written = 1

    store.insert_event({
        "event_id": event.event_id, "event_type": event.event_type.value,
        "ts": event.ts, "camera_id": event.camera_id, "frame_idx": event.frame_idx,
        "track_id": event.track_id, "zone": event.zone,
        "payload": json.dumps(event.payload),
    })
    if event.track_id is not None:
        dwell = float(event.payload.get("dwell_s", 0) or 0)
        store.upsert_track(event.camera_id, event.track_id, event.ts, event.zone, dwell)

    for alert in anomaly.check(event):
        jsonl.write(alert.model_dump_json() + "\n")
        written += 1
        store.insert_event({
            "event_id": alert.event_id, "event_type": alert.event_type.value,
            "ts": alert.ts, "camera_id": alert.camera_id, "frame_idx": alert.frame_idx,
            "track_id": alert.track_id, "zone": alert.zone,
            "payload": json.dumps(alert.payload),
        })
        store.insert_alert({
            "event_id": alert.event_id, "alert_type": alert.event_type.value,
            "ts": alert.ts, "camera_id": alert.camera_id, "zone": alert.zone,
            "severity": "critical" if alert.event_type.value == "afterhours_alert" else "warning",
            "detail": json.dumps(alert.payload),
        })
    return written


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Store Intelligence — LITE pipeline")
    p.add_argument("--source", default="data/videos/store.mp4")
    p.add_argument("--camera", default="cam-01")
    p.add_argument("--max-frames", type=int, default=0)
    p.add_argument("--show", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    s = get_settings()
    store = Store()
    anomaly = AnomalyEngine(s, camera_id=args.camera)
    layout = load_layout()
    gen = EventGenerator(camera_id=args.camera, layout=layout)

    JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    return process_video(source=args.source, camera_id=args.camera, max_frames=args.max_frames)


def process_video(source: str | int, camera_id: str = "cam-01",
                  max_frames: int = 0,
                  output_filename: str = "tracked_store.mp4") -> int:
    global _run_progress
    _run_progress["running"] = True
    _run_progress["processed_frames"] = 0
    _run_progress["total_frames"] = 0
    try:
        s = get_settings()
        store = Store()
        
        # Reset database state and truncate events.jsonl for clean demo runs
        print("[lite] Clearing database tables...")
        store.clear_tables()
        if JSONL_PATH.exists():
            try:
                JSONL_PATH.write_text("")
            except Exception:
                pass

        anomaly = AnomalyEngine(s, camera_id=camera_id)
        layout = load_layout()
        gen = EventGenerator(camera_id=camera_id, layout=layout)

        output_path = Path("data/output") / output_filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)

        source_arg = int(source) if str(source).isdigit() else source
        
        # Log starting parameters
        print(f"[lite] Input video path: {source_arg}")
        print(f"[lite] Output video path: {output_path}")

        fps = 30.0
        frame_size = None
        if isinstance(source_arg, str) and Path(source_arg).exists():
            cap = cv2.VideoCapture(source_arg)
            if cap.isOpened():
                fps_val = cap.get(cv2.CAP_PROP_FPS)
                if fps_val and fps_val > 0:
                    fps = fps_val
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                if w > 0 and h > 0:
                    frame_size = (w, h)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if max_frames and total_frames > max_frames:
                    total_frames = max_frames
                _run_progress["total_frames"] = total_frames
            cap.release()

        from ultralytics import YOLO
        print(f"[lite] loading {s.yolo_model} (CPU) ...")
        model = YOLO(s.yolo_model)

        results = model.track(
            source=source_arg, classes=[s.person_class_id], conf=s.detect_conf,
            tracker="bytetrack.yaml", persist=True, stream=True, verbose=False,
        )

        from collections import defaultdict
        track_history = defaultdict(list)

        writer = None
        frame_idx = 0
        last_tick = time.time()
        written = 0
        print(f"[lite] writing -> {output_path} and SQLite (data/store.db)")

        with open(JSONL_PATH, "a", encoding="utf-8") as jsonl:
            for res in results:
                frame_idx += 1
                _run_progress["processed_frames"] = frame_idx
                frame = res.orig_img.copy() if hasattr(res, 'orig_img') else None
                if frame is None:
                    continue

                if writer is None:
                    h, w = frame.shape[:2]
                    if frame_size is None:
                        frame_size = (w, h)
                    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"avc1"), fps, frame_size)

                if res.boxes is not None and res.boxes.id is not None:
                    ids = res.boxes.id.int().tolist()
                    xyxy = res.boxes.xyxy.tolist()
                    for tid, (x1, y1, x2, y2) in zip(ids, xyxy):
                        x1i, y1i, x2i, y2i = int(x1), int(y1), int(x2), int(y2)
                        
                        # Update track history center points
                        cx_px = int((x1i + x2i) / 2)
                        cy_px = int((y1i + y2i) / 2)
                        track_history[tid].append((cx_px, cy_px))
                        if len(track_history[tid]) > 30:
                            track_history[tid].pop(0)

                        # Draw movement trails (trajectory lines) in Purplle brand secondary color
                        for i in range(1, len(track_history[tid])):
                            cv2.line(frame, track_history[tid][i - 1], track_history[tid][i], (247, 85, 168), 2)

                        cv2.rectangle(frame, (x1i, y1i), (x2i, y2i), (0, 255, 0), 2)
                        label = f"Person #{int(tid)}"
                        text_size, baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                        text_x = x1i
                        text_y = y1i - 10 if y1i - 10 > text_size[1] + 4 else y1i + text_size[1] + 12
                        cv2.rectangle(
                            frame,
                            (text_x - 2, text_y - text_size[1] - 4),
                            (text_x + text_size[0] + 2, text_y + 4),
                            (0, 255, 0),
                            cv2.FILLED,
                        )
                        cv2.putText(frame, label, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                    (0, 0, 0), 2, lineType=cv2.LINE_AA)

                h, w = res.orig_shape
                ts = datetime.now(timezone.utc).timestamp()
                dets = []
                if res.boxes is not None and res.boxes.id is not None:
                    ids = res.boxes.id.int().tolist()
                    xyxy = res.boxes.xyxy.tolist()
                    confs = res.boxes.conf.tolist()
                    for tid, (x1, y1, x2, y2), cf in zip(ids, xyxy, confs):
                        dets.append((int(tid), ((x1 + x2) / 2) / w, ((y1 + y2) / 2) / h,
                                     [int(x1), int(y1), int(x2), int(y2)], float(cf)))

                writer.write(frame)

                for ev in gen.process_frame(frame_idx, dets, ts):
                    written += persist(store, anomaly, jsonl, ev)

                if time.time() - last_tick >= 1.0:
                    for ev in gen.occupancy_snapshot(frame_idx, ts):
                        written += persist(store, anomaly, jsonl, ev)
                    last_tick = time.time()
                    jsonl.flush()
                    print(f"[lite] frame={frame_idx} active={len(gen.tracks)} written={written}",
                          end="\r")

                if max_frames and frame_idx >= max_frames:
                    break

        if writer is not None:
            writer.release()

        print(f"\n[lite] done.")
        print(f"[lite] Input video path: {source_arg}")
        print(f"[lite] Output video path: {output_path}")
        print(f"[lite] Total processed frames: {frame_idx}")
        return 0
    finally:
        _run_progress["running"] = False


if __name__ == "__main__":
    sys.exit(main())
