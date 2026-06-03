"""Real-time anomaly detection.

Three explainable detectors, all operating on the event stream:

1. Crowding       — rolling z-score of per-zone occupancy + an absolute floor.
2. Excessive dwell — a single track sitting in one zone too long.
3. After-hours    — any presence outside configured store hours.

We deliberately avoid a heavy learned model: these rules need no labels, run in
O(1) per event, and are trivial to justify in an interview. Trade-offs are noted
in docs/DECISIONS.md.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from statistics import mean, pstdev

from backend.config import Settings
from backend.events import Event, EventType, make_event


class AnomalyEngine:
    def __init__(self, settings: Settings, camera_id: str = "cam-01") -> None:
        self.s = settings
        self.camera_id = camera_id
        # rolling occupancy history per zone: deque[(ts_epoch, count)]
        self._occ: dict[str, deque[tuple[float, int]]] = defaultdict(
            lambda: deque(maxlen=600)
        )
        # de-dupe alerts so we don't spam (zone/track -> last alert epoch)
        self._cooldown: dict[str, float] = {}
        self.cooldown_s = 15.0

    # ---- helpers ----
    def _cooled_down(self, key: str, now: float) -> bool:
        last = self._cooldown.get(key)
        if last is not None and now - last < self.cooldown_s:
            return False
        self._cooldown[key] = now
        return True

    @staticmethod
    def _epoch(ts_iso: str) -> float:
        return datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).timestamp()

    # ---- main entry ----
    def check(self, event: Event) -> list[Event]:
        """Return a list of alert events triggered by this incoming event."""
        alerts: list[Event] = []
        now = self._epoch(event.ts)

        # 3) after-hours: any track/zone activity outside opening hours
        if event.event_type in (EventType.zone_enter, EventType.track_started):
            hour = datetime.fromisoformat(event.ts.replace("Z", "+00:00")).hour
            if not (self.s.store_open_hour <= hour < self.s.store_close_hour):
                if self._cooled_down(f"afterhours:{event.zone}", now):
                    alerts.append(make_event(
                        EventType.afterhours_alert, event.camera_id,
                        frame_idx=event.frame_idx, zone=event.zone,
                        payload={"hour": hour, "count": 1},
                    ))

        # 2) excessive dwell: zone_exit carries dwell_s
        if event.event_type == EventType.zone_exit:
            dwell = float(event.payload.get("dwell_s", 0))
            if dwell >= self.s.dwell_alert_seconds:
                if self._cooled_down(f"dwell:{event.track_id}", now):
                    alerts.append(make_event(
                        EventType.dwell_alert, event.camera_id,
                        frame_idx=event.frame_idx, track_id=event.track_id,
                        zone=event.zone, payload={"dwell_s": dwell},
                    ))

        # 1) crowding: rolling z-score on occupancy ticks
        if event.event_type == EventType.occupancy_tick and event.zone:
            count = int(event.payload.get("count", 0))
            hist = self._occ[event.zone]
            window_start = now - self.s.anomaly_window
            counts = [c for (t, c) in hist if t >= window_start]
            hist.append((now, count))

            if len(counts) >= 10 and count >= self.s.crowd_min_count:
                mu = mean(counts)
                sigma = pstdev(counts) or 1e-9
                z = (count - mu) / sigma
                if z >= self.s.crowd_zscore:
                    if self._cooled_down(f"crowd:{event.zone}", now):
                        alerts.append(make_event(
                            EventType.crowd_alert, event.camera_id,
                            frame_idx=event.frame_idx, zone=event.zone,
                            payload={"count": count, "zscore": round(z, 2),
                                     "threshold": self.s.crowd_zscore,
                                     "baseline_mean": round(mu, 2)},
                        ))

        return alerts
