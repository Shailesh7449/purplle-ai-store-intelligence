"""Event envelope + factory helpers shared by pipeline and consumer.

Keeping the event contract in one Pydantic model guarantees the producer and
the consumer can never disagree about the shape of an event.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


class EventType(str, Enum):
    track_started = "track_started"
    track_ended = "track_ended"
    zone_enter = "zone_enter"
    zone_exit = "zone_exit"
    line_cross = "line_cross"
    occupancy_tick = "occupancy_tick"
    crowd_alert = "crowd_alert"
    dwell_alert = "dwell_alert"
    afterhours_alert = "afterhours_alert"


ALERT_TYPES = {
    EventType.crowd_alert,
    EventType.dwell_alert,
    EventType.afterhours_alert,
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: int = SCHEMA_VERSION
    event_type: EventType
    ts: str = Field(default_factory=_utcnow_iso)
    camera_id: str
    frame_idx: int = 0
    track_id: Optional[int] = None
    zone: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_stream_fields(self) -> dict[str, str]:
        """Redis Streams stores flat string fields; we ship the JSON body."""
        return {"data": self.model_dump_json()}

    @classmethod
    def from_stream(cls, fields: dict[str, str]) -> "Event":
        raw = fields.get("data") or fields.get(b"data")  # type: ignore[arg-type]
        if isinstance(raw, bytes):
            raw = raw.decode()
        return cls.model_validate_json(raw)

    @property
    def is_alert(self) -> bool:
        return self.event_type in ALERT_TYPES


def make_event(event_type: EventType, camera_id: str, **kwargs: Any) -> Event:
    """Convenience factory used throughout the pipeline."""
    return Event(event_type=event_type, camera_id=camera_id, **kwargs)
