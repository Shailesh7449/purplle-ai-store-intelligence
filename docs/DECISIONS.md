# Design Decisions & Trade-offs

The challenge explicitly rewards *how you think* and *how you explain trade-offs*. This is the
document to walk an interviewer through.

## 1. Event-driven architecture (ingest → bus → process → store → serve)
**Decision:** decouple the vision producer, the event bus, the persistence/anomaly consumer, and
the API.
**Why:** each stage scales and fails independently. The camera can run on an edge box, multiple
consumers can share load, and the API stays responsive because it only reads aggregates.
**Trade-off:** more moving parts than a monolith. Mitigated by Docker Compose (one command) and a
single shared config/event contract.

## 2. Redis Streams as the event bus (not Kafka)
**Decision:** use Redis Streams with consumer groups.
**Why:** identical mental model to Kafka — append-only log, offsets, consumer groups, acks,
replay (`XRANGE`) — but near-zero ops and trivial to Dockerise for a 5-day build.
**Trade-off:** Kafka wins at very high throughput, multi-broker durability, and ecosystem
(Connect, ksqlDB). **Migration path:** we never use Redis-specific semantics, so swapping in
`aiokafka`/`confluent-kafka` is a localized change in `pipeline/run.py` (produce) and
`consumer/main.py` (consume). Documented intentionally.

## 3. ByteTrack (Ultralytics built-in) over DeepSORT
**Decision:** track with `model.track(tracker="bytetrack.yaml", persist=True)`.
**Why:** strong accuracy, no separate ReID network to train/ship, one dependency, and tunable via
a YAML (`track_buffer`, `match_thresh`) for occlusion robustness.
**Trade-off:** DeepSORT's appearance embedding re-identifies people better after long occlusions
or across cameras. For single-camera store analytics, ByteTrack's motion+IoU is the right
cost/benefit. Cross-camera ReID is noted as future work.

## 4. YOLOv8n as the default detector
**Decision:** ship `yolov8n` (nano) by default.
**Why:** runs in real time on CPU, downloads automatically, good enough for person detection.
**Trade-off:** lower mAP than `yolov8s/m/x`. Model is a single env var (`YOLO_MODEL`) so you can
trade speed for accuracy without code changes.

## 5. Rule + statistics anomaly detection (not a learned model)
**Decision:** z-score crowding + threshold dwell + after-hours rules.
**Why:** **explainable**, needs **no labelled data**, runs in O(1) per event, and every alert can
be justified ("occupancy was 2.5σ above the 60s baseline"). Perfect for an interview defence.
**Trade-off:** less adaptive than an autoencoder/Isolation-Forest that learns "normal". The
rolling z-score already adapts to each zone's baseline; a learned model is listed as future work
with a clear upgrade path (same event stream as training data).

## 6. Normalised geometry for zones/lines
**Decision:** zones and counting lines stored as fractions of frame size (0..1).
**Why:** resolution-independent — the same config works for 720p or 4K cameras.
**Trade-off:** assumes a fixed camera view (fine for CCTV).

## 7. Raw SQL + PostgreSQL (no ORM)
**Decision:** psycopg3 with hand-written SQL; JSONB for flexible payloads.
**Why:** the analytics are aggregate-heavy (window functions, `date_bin`, `DISTINCT ON`), which
read better as SQL than ORM expressions; JSONB keeps the event payload flexible while the envelope
stays typed/indexed.
**Trade-off:** less compile-time safety than an ORM. Mitigated by a typed `Event` model and a thin,
well-tested data layer.

## 8. HTML/JS + Chart.js dashboard (not React)
**Decision:** static dashboard served by FastAPI; REST polling + a WebSocket for live events.
**Why:** one deployable unit, no JS build step, fast to ship, clean enough to demo.
**Trade-off:** less component reuse than React. Acceptable for a focused dashboard.

## 9. Idempotency & at-least-once delivery
**Decision:** every event has a UUID; DB inserts use `ON CONFLICT DO NOTHING`; consumer uses
`XREADGROUP` + `XACK`.
**Why:** safe to replay the stream or restart the consumer without double-counting.
**Trade-off:** at-least-once (not exactly-once) — handled by idempotent writes.

## What I'd do next with more time
- Cross-camera person ReID for multi-camera stores.
- Learned anomaly model (Isolation Forest) trained on collected events.
- Heatmaps of movement & shelf-interaction (pose / product detection).
- Auth + multi-tenant store isolation on the API.
- Prometheus/Grafana for pipeline + consumer metrics (lag, fps, drop rate).
- Kafka swap for high-throughput, multi-store deployments.
