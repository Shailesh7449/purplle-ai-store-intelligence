# CHOICES.md — Engineering Decisions & Trade-offs

> Required by the evaluation acceptance gate. Each decision states the option chosen,
> why, and what it costs — demonstrating ownership rather than generic explanations.

## 1. Treat this as a *conversion-rate* system, not a CCTV demo
**Decision:** make **conversion = transactions ÷ footfall** the centrepiece, joining
CCTV-derived footfall with the POS sales CSV.
**Why:** the framework explicitly names "store conversion rate" as the goal and weights
**API + Business Logic at 35/100** (the largest block). Building the funnel correctly
scores more than perfect detection.
**Trade-off:** less time on CV tuning — acceptable, since the rubric says detection
accuracy is *not* the point.

## 2. Session-based counting via ByteTrack track IDs
**Decision:** footfall and every funnel stage count **distinct `track_id`s**.
**Why:** directly satisfies "session-based, no double counting" in the funnel criteria
and handles re-entry / line jitter for free.
**Trade-off:** if the tracker drops and re-acquires an ID, one visitor can be counted
twice. Mitigated by `track_buffer`; cross-camera ReID noted as future work.

## 3. ByteTrack (built-in) over DeepSORT
**Decision:** Ultralytics' built-in ByteTrack.
**Why:** strong accuracy, **no separate ReID model** to ship, one dependency, real-time
on CPU.
**Trade-off:** weaker re-identification after long occlusions than appearance-based
DeepSORT — fine for single-camera footfall.

## 4. YOLOv8n + CPU-only PyTorch
**Decision:** nano model, install `torch` from the CPU wheel index.
**Why:** runs on a laptop with no GPU and **~5 GB less disk** than the default CUDA
build (a real constraint encountered during the build). Model is one env var if more
accuracy is needed.
**Trade-off:** lower mAP than larger models — acceptable per the rubric.

## 5. Two profiles: SQLite/jsonl "lite" **and** Postgres/Redis "full"
**Decision:** ship both. Lite (SQLite + `events.jsonl`) is the dev/demo run; the full
Docker stack (Postgres + Redis Streams + consumer) satisfies `docker compose up`.
**Why:** the acceptance gate requires `docker compose up`, but a solo build on limited
disk needs a lean path to iterate fast. Same application code, swappable storage.
**Trade-off:** two storage layers to maintain — justified by the gate + dev speed.

## 6. `events.jsonl` as a replayable log instead of Kafka (in lite)
**Decision:** append events to a JSON-lines file; `scripts/ingest_jsonl.py` replays it.
**Why:** a file gives append-only, replayable, inspectable semantics with zero infra —
ideal under time/disk constraints. Kafka/Redis remain in the full profile.
**Trade-off:** no multi-consumer fan-out or backpressure in lite — not needed for a
single-store batch demo.

## 7. Rule + statistics anomaly detection (no trained model)
**Decision:** rolling z-score crowding, threshold dwell, after-hours rules.
**Why:** explainable, **needs no labels**, real-time, and every alert is justifiable —
matching "logical and meaningful anomaly detection".
**Trade-off:** less adaptive than a learned model; the rolling baseline already adapts
per zone.

## 8. Raw SQL over an ORM
**Decision:** stdlib `sqlite3` / psycopg with hand-written SQL + window functions.
**Why:** the analytics (DISTINCT-ID counts, hourly buckets, funnel) are clearer and
more correct as explicit SQL; keeps the data model transparent for reviewers.
**Trade-off:** less compile-time safety — mitigated by typed event models + tests.

## 9. HTML/JS + Chart.js dashboard (no React/Streamlit)
**Decision:** static dashboard served by FastAPI, polling REST.
**Why:** one deployable unit, no extra build step or heavy install, clean enough to demo
in the reviewer's 2-minute window.
**Trade-off:** less component structure than React — fine for a focused dashboard.

## 10. No hardcoded outputs (integrity)
**Decision:** every metric is recomputed from `events.db` + the sales CSV per request.
**Why:** the integrity check caps scores at 50 for hardcoded/static outputs. Swapping
the video or CSV changes every number — easy to demonstrate live.

## What I'd do next with more time
- Cross-camera person ReID to merge multi-angle footage into one footfall count.
- Staff exclusion via uniform/zone heuristics or a small classifier.
- Per-zone conversion attribution (which counter a buyer browsed before purchase).
- Learned anomaly model trained on the collected event log.
- Prometheus/Grafana for pipeline FPS, consumer lag, drop rate.
