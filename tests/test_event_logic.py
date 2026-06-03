"""Unit tests for the pure event-generation logic (no YOLO / Redis / DB)."""
from pipeline.event_logic import EventGenerator
from pipeline.zones import default_layout
from backend.events import EventType


def make_gen():
    return EventGenerator("cam-test", default_layout(), lost_after_frames=3)


def test_track_started_and_zone_enter():
    gen = make_gen()
    # point in 'entrance' zone (x<0.35)
    events = gen.process_frame(1, [(1, 0.1, 0.5, [0, 0, 50, 100], 0.9)], ts_epoch=1000.0)
    types = [e.event_type for e in events]
    assert EventType.track_started in types
    assert EventType.zone_enter in types
    enter = next(e for e in events if e.event_type == EventType.zone_enter)
    assert enter.zone == "entrance"


def test_zone_transition_emits_exit_then_enter():
    gen = make_gen()
    gen.process_frame(1, [(1, 0.1, 0.5, [0, 0, 1, 1], 0.9)], ts_epoch=1000.0)
    events = gen.process_frame(2, [(1, 0.5, 0.5, [0, 0, 1, 1], 0.9)], ts_epoch=1010.0)
    types = [e.event_type for e in events]
    assert EventType.zone_exit in types
    assert EventType.zone_enter in types
    exit_ev = next(e for e in events if e.event_type == EventType.zone_exit)
    assert exit_ev.zone == "entrance"
    assert exit_ev.payload["dwell_s"] == 10.0


def test_line_cross_direction():
    gen = make_gen()
    # door line is vertical at x=0.15; start right of it, move to left -> 'in'
    gen.process_frame(1, [(1, 0.20, 0.5, [0, 0, 1, 1], 0.9)], ts_epoch=1000.0)
    events = gen.process_frame(2, [(1, 0.05, 0.5, [0, 0, 1, 1], 0.9)], ts_epoch=1001.0)
    crosses = [e for e in events if e.event_type == EventType.line_cross]
    assert crosses, "expected a line_cross event"
    assert crosses[0].payload["direction"] in ("in", "out")


def test_track_ended_after_lost():
    gen = make_gen()
    gen.process_frame(1, [(1, 0.1, 0.5, [0, 0, 1, 1], 0.9)], ts_epoch=1000.0)
    # no detections for > lost_after_frames
    gen.process_frame(2, [], ts_epoch=1001.0)
    gen.process_frame(3, [], ts_epoch=1002.0)
    events = gen.process_frame(10, [], ts_epoch=1010.0)
    assert any(e.event_type == EventType.track_ended for e in events)


def test_occupancy_snapshot_counts_zones():
    gen = make_gen()
    gen.process_frame(1, [
        (1, 0.5, 0.10, [0, 0, 1, 1], 0.9),  # shelf_top
        (2, 0.5, 0.50, [0, 0, 1, 1], 0.9),  # foh
        (3, 0.5, 0.85, [0, 0, 1, 1], 0.9),  # shelf_bottom
    ], ts_epoch=1000.0)
    snaps = gen.occupancy_snapshot(1, ts_epoch=1000.0)
    by_zone = {e.zone: e.payload["count"] for e in snaps}
    assert by_zone == {"entrance": 0, "shelf_top": 1, "foh": 1, "shelf_bottom": 1, "cash_counter": 0}
