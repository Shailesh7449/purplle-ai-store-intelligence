# Event Schema

Every meaningful thing the system observes becomes an **event**: a small, self-describing,
append-only JSON record. Events flow `pipeline → Redis Stream → consumer → PostgreSQL`.

## Design principles
- **Flat & versioned** — `schema_version` lets us evolve without breaking consumers.
- **Self-describing** — each event carries `camera_id`, `zone`, `ts`, and a `payload`.
- **Idempotent-friendly** — `event_id` (UUID) lets the consumer dedupe on replay.
- **Append-only** — events are facts that happened; aggregates are derived downstream.

## Envelope (common to all events)

| Field | Type | Description |
|---|---|---|
| `event_id` | string (uuid) | Unique id, used for dedupe |
| `schema_version` | int | Currently `1` |
| `event_type` | enum | See table below |
| `ts` | string (ISO-8601, UTC) | When the event occurred (frame timestamp) |
| `camera_id` | string | Source camera / video id |
| `frame_idx` | int | Frame index in the source |
| `track_id` | int \| null | Tracked object id (ByteTrack), null for aggregate events |
| `zone` | string \| null | Zone name where it happened |
| `payload` | object | Event-type-specific fields |

## Event types

| `event_type` | When emitted | Key `payload` fields |
|---|---|---|
| `track_started` | A new person id appears | `bbox`, `conf` |
| `track_ended` | A person id is lost (left frame) | `duration_s`, `last_zone` |
| `zone_enter` | Track enters a defined zone | `bbox` |
| `zone_exit` | Track leaves a zone | `dwell_s` |
| `line_cross` | Track crosses a counting line | `direction` (`in`/`out`) |
| `occupancy_tick` | Periodic per-zone snapshot (e.g., 1/sec) | `count` |
| `crowd_alert` | Crowding anomaly fired | `count`, `zscore`, `threshold` |
| `dwell_alert` | Excessive dwell anomaly | `track_id`, `dwell_s` |
| `afterhours_alert` | Motion outside store hours | `count` |

## Example
```json
{
  "event_id": "0f5e2b6a-7b1c-4e2a-9a55-2a1c0d6b9f10",
  "schema_version": 1,
  "event_type": "zone_enter",
  "ts": "2026-05-30T12:34:56.120Z",
  "camera_id": "cam-01",
  "frame_idx": 1842,
  "track_id": 27,
  "zone": "checkout",
  "payload": { "bbox": [320, 210, 410, 480] }
}
```

## Why Redis Streams as the bus
A Redis Stream is an append-only log with consumer groups, offsets and acknowledgements —
the same mental model as Kafka. We get durability, replay (`XRANGE`), at-least-once delivery
(`XREADGROUP` + `XACK`), and horizontal scaling (multiple consumers in a group) with almost no
operational overhead. The migration path to Kafka is 1:1 because we never depend on
Redis-specific semantics. See `docs/DECISIONS.md`.
