# 4-Day Execution Plan (Round 2)

Challenge window: **May 29 → Jun 03, 2026**. Today is **May 30** — you effectively have ~4 working
days. This plan is ordered so that **you always have something that runs**. Ship vertically, not
horizontally.

> The scaffold in this repo already covers Day 1 + most of Day 2. Use the rest to make it *yours*,
> get real footage working, and polish the story.

## Day 1 (✅ mostly done by this scaffold) — Skeleton that runs end-to-end
- [x] Repo structure, config, event schema, Docker Compose.
- [x] `pipeline → Redis → consumer → Postgres → API → dashboard` path.
- [x] `seed_demo.py` to push synthetic events (demo without YOLO).
- **Your task:** `docker compose up`, run `python scripts/seed_demo.py`, confirm the dashboard
  shows KPIs, zones, alerts, and a live feed. *Get the green "live" dot.*

## Day 2 — Real vision on real footage
- [ ] Drop a real CCTV clip at `data/videos/store.mp4` (do **not** commit it).
- [ ] Run `python -m pipeline.run --source data/videos/store.mp4 --show`.
- [ ] Tune zones/line in `pipeline/zones.py` to match your video's layout.
- [ ] Tune `DETECT_CONF`, `bytetrack.yaml` (`track_buffer`, `match_thresh`) for stable IDs.
- [ ] Verify events land in Postgres and surface on the dashboard.

## Day 3 — Intelligence + robustness
- [ ] Validate the 3 anomaly detectors fire on real data; tune thresholds in `.env`.
- [ ] Add 1 differentiator that fits your footage (pick ONE):
      heatmap of dwell, queue-length at checkout, or product-shelf interaction.
- [ ] Make `pytest` green; add a test for any new logic.
- [ ] Record pipeline FPS and write it in the README (shows production awareness).

## Day 4 — Polish, document, submit
- [ ] Tighten README: architecture diagram, screenshots/GIF of the dashboard.
- [ ] Finish `docs/DECISIONS.md` with YOUR reasoning (interviewers read this).
- [ ] Record a 2–3 min demo video (problem → architecture → live demo → trade-offs).
- [ ] Final check: clone fresh, `docker compose up`, seed, confirm it works.
- [ ] Push to GitHub **without** dataset/video (`.gitignore` already handles it).

## What scores points (from the brief)
| They evaluate | Where this repo shows it |
|---|---|
| System thinking | event-driven architecture, decoupled stages |
| Practical AI | YOLOv8 + ByteTrack, tuned, real-time |
| Production readiness | Docker, health checks, idempotency, graceful shutdown, tests |
| Ownership / decisions | `docs/DECISIONS.md` trade-offs |
| Technical reasoning / docs | README + EVENT_SCHEMA + API + this plan |

## Demo-day talking points (rehearse these)
1. "I built it event-driven so each stage scales/fails independently."
2. "Redis Streams gives me Kafka-like semantics with near-zero ops; here's my migration path."
3. "ByteTrack over DeepSORT because single-camera store analytics doesn't need appearance ReID."
4. "Anomalies are statistical + rule-based so every alert is explainable and needs no labels."
5. "Everything is idempotent and replay-safe; one command runs the whole system."

## Common mistakes to avoid (from your mentor notes)
- ❌ Trying to build *everything*. ✅ Small but complete.
- ❌ Copy-pasting huge pipelines you can't explain. ✅ Own every line.
- ❌ Broken setup on a fresh clone. ✅ Test `docker compose up` clean.
- ❌ No docs. ✅ README + decisions + demo video.
