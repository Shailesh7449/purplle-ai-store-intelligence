"""Stateful translation of per-frame tracks into semantic events.

Input  : for each frame, a list of (track_id, cx, cy, bbox, conf) in NORMALISED coords.
Output : a list of Event objects (zone_enter/exit, line_cross, track start/end, occupancy).

This module is pure logic (no I/O), which makes it unit-testable without YOLO,
Redis or a video — see tests/test_event_logic.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.events import Event, EventType, make_event
from pipeline.zones import StoreLayout


@dataclass
class TrackState:
    track_id: int
    zone: str | None = None
    zone_since: float = 0.0          # epoch seconds
    last_side: dict[str, float] = field(default_factory=dict)
    last_seen_frame: int = 0
    first_seen: float = 0.0


class EventGenerator:
    def __init__(self, camera_id: str, layout: StoreLayout,
                 lost_after_frames: int = 30) -> None:
        self.camera_id = camera_id
        self.layout = layout
        self.lost_after_frames = lost_after_frames
        self.tracks: dict[int, TrackState] = {}

    def _now(self, ts: float | None) -> float:
        return ts if ts is not None else datetime.now(timezone.utc).timestamp()

    def process_frame(
        self,
        frame_idx: int,
        detections: list[tuple[int, float, float, list[int], float]],
        ts_epoch: float | None = None,
    ) -> list[Event]:
        now = self._now(ts_epoch)
        events: list[Event] = []
        seen_ids: set[int] = set()

        for track_id, cx, cy, bbox, conf in detections:
            seen_ids.add(track_id)
            st = self.tracks.get(track_id)
            if st is None:
                st = TrackState(track_id=track_id, first_seen=now)
                self.tracks[track_id] = st
                events.append(make_event(
                    EventType.track_started, self.camera_id, frame_idx=frame_idx,
                    track_id=track_id, payload={"bbox": bbox, "conf": round(conf, 3)},
                ))

            st.last_seen_frame = frame_idx

            # --- zone transitions ---
            new_zone = self.layout.zone_for_point(cx, cy)
            if new_zone != st.zone:
                if st.zone is not None:
                    dwell = round(now - st.zone_since, 2)
                    events.append(make_event(
                        EventType.zone_exit, self.camera_id, frame_idx=frame_idx,
                        track_id=track_id, zone=st.zone, payload={"dwell_s": dwell},
                    ))
                if new_zone is not None:
                    events.append(make_event(
                        EventType.zone_enter, self.camera_id, frame_idx=frame_idx,
                        track_id=track_id, zone=new_zone, payload={"bbox": bbox},
                    ))
                st.zone = new_zone
                st.zone_since = now

            # --- line crossings ---
            for line in self.layout.lines:
                side = line.side(cx, cy)
                prev = st.last_side.get(line.name)
                if prev is not None and prev != 0 and (prev > 0) != (side > 0):
                    direction = "in" if side < 0 else "out"
                    events.append(make_event(
                        EventType.line_cross, self.camera_id, frame_idx=frame_idx,
                        track_id=track_id, zone=line.name,
                        payload={"direction": direction},
                    ))
                st.last_side[line.name] = side

        # --- expire lost tracks ---
        lost = [
            tid for tid, st in self.tracks.items()
            if frame_idx - st.last_seen_frame > self.lost_after_frames
            and tid not in seen_ids
        ]
        for tid in lost:
            st = self.tracks.pop(tid)
            events.append(make_event(
                EventType.track_ended, self.camera_id, frame_idx=frame_idx,
                track_id=tid, zone=st.zone,
                payload={"duration_s": round(now - st.first_seen, 2),
                         "last_zone": st.zone},
            ))

        return events

    def occupancy_snapshot(self, frame_idx: int,
                           ts_epoch: float | None = None) -> list[Event]:
        """Emit one occupancy_tick per zone (call ~1x/second)."""
        counts: dict[str, int] = {z.name: 0 for z in self.layout.zones}
        for st in self.tracks.values():
            if st.zone in counts:
                counts[st.zone] += 1
        return [
            make_event(
                EventType.occupancy_tick, self.camera_id, frame_idx=frame_idx,
                zone=zone, payload={"count": count},
            )
            for zone, count in counts.items()
        ]
