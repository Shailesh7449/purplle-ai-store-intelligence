"""Generate a synthetic 'CCTV' video so the full pipeline can be demoed without
a real dataset (which must NOT be committed anyway).

Draws moving rectangles that loosely resemble people walking across a store, so
YOLOv8 won't detect them as persons — this file is for *plumbing* demos. For a
real detection demo, drop a real CCTV clip at data/videos/store.mp4.

Usage: python scripts/make_sample_video.py
"""
import os as _os, sys as _sys  # _PROJECT_ROOT_BOOTSTRAP
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


import random

import cv2
import numpy as np

W, H, FPS, SECONDS = 960, 540, 20, 30
OUT = "data/videos/store.mp4"


def main() -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(OUT, fourcc, FPS, (W, H))
    people = [{"x": random.randint(0, W), "y": random.randint(80, H - 80),
               "vx": random.choice([-3, -2, 2, 3]), "vy": random.choice([-1, 1])}
              for _ in range(6)]
    for _ in range(FPS * SECONDS):
        frame = np.full((H, W, 3), (30, 30, 35), np.uint8)
        # draw zone separators
        for fx in (0.35, 0.7):
            cv2.line(frame, (int(W * fx), 0), (int(W * fx), H), (60, 60, 80), 1)
        for p in people:
            p["x"] += p["vx"]; p["y"] += p["vy"]
            if p["x"] < 0 or p["x"] > W: p["vx"] *= -1
            if p["y"] < 60 or p["y"] > H - 60: p["vy"] *= -1
            cv2.rectangle(frame, (p["x"] - 12, p["y"] - 30),
                          (p["x"] + 12, p["y"] + 30), (200, 180, 120), -1)
        vw.write(frame)
    vw.release()
    print(f"[make_sample_video] wrote {OUT} ({W}x{H}, {FPS}fps, {SECONDS}s)")


if __name__ == "__main__":
    main()
