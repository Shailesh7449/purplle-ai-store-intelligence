"""Unit tests for the anomaly engine (pure logic, no I/O)."""
from backend.config import Settings
from backend.events import EventType, make_event
from consumer.anomaly import AnomalyEngine


def settings(**kw):
    base = dict(store_open_hour=9, store_close_hour=21, dwell_alert_seconds=120,
                crowd_zscore=2.5, crowd_min_count=5, anomaly_window=60)
    base.update(kw)
    return Settings(**base)


def test_dwell_alert_fires():
    eng = AnomalyEngine(settings())
    ev = make_event(EventType.zone_exit, "cam-01", track_id=7, zone="aisle",
                    ts="2026-05-30T12:00:00+00:00", payload={"dwell_s": 200})
    alerts = eng.check(ev)
    assert any(a.event_type == EventType.dwell_alert for a in alerts)


def test_dwell_alert_does_not_fire_below_threshold():
    eng = AnomalyEngine(settings())
    ev = make_event(EventType.zone_exit, "cam-01", track_id=7, zone="aisle",
                    ts="2026-05-30T12:00:00+00:00", payload={"dwell_s": 30})
    assert eng.check(ev) == []


def test_afterhours_alert_fires():
    eng = AnomalyEngine(settings())
    ev = make_event(EventType.zone_enter, "cam-01", track_id=1, zone="entrance",
                    ts="2026-05-30T03:00:00+00:00", payload={})
    alerts = eng.check(ev)
    assert any(a.event_type == EventType.afterhours_alert for a in alerts)


def test_crowd_alert_on_spike():
    eng = AnomalyEngine(settings())
    base_t = 1_700_000_000
    # build a calm baseline of ~2 people for 20 ticks
    for i in range(20):
        ev = make_event(EventType.occupancy_tick, "cam-01", zone="checkout",
                        ts=_iso(base_t + i), payload={"count": 2})
        eng.check(ev)
    # sudden spike
    spike = make_event(EventType.occupancy_tick, "cam-01", zone="checkout",
                       ts=_iso(base_t + 21), payload={"count": 15})
    alerts = eng.check(spike)
    assert any(a.event_type == EventType.crowd_alert for a in alerts)


def _iso(epoch: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
