# AI-Assisted Engineering Log

The challenge explicitly encourages AI tools and asks you to document *how* you used
them — what you accepted, and what you rejected. This is easy points; keep it honest
and specific. Below is a template + real examples from this project. **Edit it to
reflect your own decisions.**

## How I used AI
I used an AI coding assistant as a *pair engineer*: to scaffold boilerplate, propose
architectures, and sanity-check trade-offs. I reviewed every suggestion and made the
final call. Detection/tracking uses off-the-shelf models (YOLOv8 + ByteTrack), per the
challenge's "use any model/library" guidance — my engineering effort went into the
**event schema, API correctness, anomaly logic, and data flow**, which is where the
marks are.

## Decisions: accepted vs. rejected

| AI suggested | My decision | Reasoning |
|---|---|---|
| Full Kafka + Postgres + K8s stack | ❌ Rejected for the build; kept as documented "future" | Overkill for a solo 4-day build on a 10 GB laptop. Lite mode (SQLite + jsonl) ships faster and still demonstrates the architecture. |
| Redis Streams for the event bus | ⚠️ Kept in repo, **not** in lite run | A file (`events.jsonl`) gives replayable-log semantics with zero infra. |
| DeepSORT for tracking | ❌ Rejected | ByteTrack (built into Ultralytics) needs no separate ReID model — one dependency, real-time on CPU. |
| Train a custom anomaly model | ❌ Rejected | Rule + rolling z-score is explainable, needs no labels, runs in real time. Defensible in interview. |
| YOLOv8x (most accurate) | ❌ Rejected → **YOLOv8n** | Nano runs in real time on CPU and fits disk; accuracy is "good enough" since the rubric isn't grading detection precision. |
| CPU-only torch via `--index-url` | ✅ Accepted | Cut the Docker image / install by ~5 GB of unused CUDA libraries. |
| Pydantic models for the event envelope | ✅ Accepted | Guarantees producer/consumer agree on schema; gives free validation. |
| Idempotent writes (`INSERT OR IGNORE` on `event_id`) | ✅ Accepted | Makes replay/restart safe — no double counting. |

## Prompts that worked well (examples)
- "Design a flat, versioned event schema for store CCTV analytics with an envelope +
  type-specific payload, and explain the trade-offs."
- "Give me a ByteTrack-based person counter that emits zone-enter/exit and line-cross
  events; keep the geometry resolution-independent."
- "Convert this Postgres+Redis design to a SQLite + jsonl 'lite' mode that runs with
  only Python, preserving the same API."

## What I verified myself (did NOT blindly trust AI)
- Ran the full pipeline end-to-end and confirmed events land in SQLite and surface on
  the API/dashboard.
- Wrote unit tests for the pure event logic and anomaly rules (`tests/`).
- Checked the schema against the dataset's `assertions.py` / `sample_events.jsonl`
  before finalising field names. *(⚠️ Do this once you have those files.)*

> **TODO for you:** add 2–3 concrete moments where you overrode or corrected the AI on
> *your* dataset — graders love specifics.
