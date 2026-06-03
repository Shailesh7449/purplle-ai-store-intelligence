# API Reference

Base URL: `http://localhost:8000`  ·  Interactive docs: `http://localhost:8000/docs`

## `GET /api/health`
Liveness + dependency checks.
```json
{ "status": "healthy", "checks": { "api": "ok", "postgres": "ok", "redis": "ok" } }
```

## `GET /api/metrics/summary`
Live KPIs for the dashboard header.
```json
{
  "current_occupancy": 7,
  "total_entries": 142,
  "total_exits": 135,
  "unique_visitors": 88,
  "active_alerts": 1,
  "total_events": 5021
}
```

## `GET /api/zones`
Per-zone occupancy and average dwell.
```json
[
  { "zone": "entrance", "current_count": 2, "avg_dwell_s": 8.4, "visits": 53 },
  { "zone": "aisle",    "current_count": 4, "avg_dwell_s": 41.2, "visits": 61 },
  { "zone": "checkout", "current_count": 1, "avg_dwell_s": 95.7, "visits": 40 }
]
```

## `GET /api/events`
Recent raw events. Query params: `limit` (≤500), `event_type`, `zone`.
```
GET /api/events?event_type=zone_enter&zone=checkout&limit=20
```

## `GET /api/alerts`
Recent anomaly alerts. Query param: `limit` (≤500).
```json
[
  { "alert_type": "crowd_alert", "ts": "2026-05-30T12:41:03+00:00",
    "zone": "checkout", "severity": "warning",
    "detail": { "count": 12, "zscore": 3.1, "threshold": 2.5 } }
]
```

## `GET /api/timeseries/footfall`
Entries/exits bucketed for the footfall chart. Params: `bucket_seconds`, `window_minutes`.
```json
[ { "bucket": "12:40", "entries": 9, "exits": 7 },
  { "bucket": "12:41", "entries": 12, "exits": 10 } ]
```

## `WS /ws/live`
WebSocket that streams each new event as JSON (plus periodic `{"type":"heartbeat"}`),
tailing the Redis Stream from connection time. Used by the live event feed.
