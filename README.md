# 🛍️ Purplle Store Intelligence System — Tech Challenge 2026 (Round 2)

Turn **raw CCTV footage + POS sales** into the metric that matters: **store conversion rate**.

> **Conversion rate = transactions ÷ footfall.**
> Footfall is extracted from CCTV (detect + track people entering). Transactions come
> from the POS sales export. The system joins them into live metrics, a conversion
> **funnel**, and a dashboard.

Built to the official **Evaluation Framework**: functional correctness, engineering
judgment, and clear reasoning over model complexity.

---

## ⚡ Quick start

### Acceptance-gate command (lite stack, minimal disk)
```bash
docker compose up --build
# /metrics : http://localhost:8000/metrics
# /funnel  : http://localhost:8000/funnel
# dashboard: http://localhost:8000
```
The container auto-seeds demo events on first run, so `/metrics` returns a real,
non-trivial value immediately. Add **real footfall** by running the pipeline on a video
(below).

### Run locally without Docker (fastest for dev)
```bash
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-lite.txt

python scripts/seed_lite.py          # instant demo data (no video/torch needed)
uvicorn backend.main_lite:app        # -> http://localhost:8000
```
Full lite guide: [`RUN_LITE.md`](RUN_LITE.md).

### Process a real CCTV video
```bash
python -m pipeline.run_lite --source data/videos/store.mp4   # writes events -> SQLite + jsonl
uvicorn backend.main_lite:app
```

---

## 📡 Key endpoints (graded)

| Endpoint | Returns |
|---|---|
| `GET /metrics` | **conversion rate**, footfall, transactions, customers, units, revenue, avg basket |
| `GET /funnel` | session-based funnel: entered → browsed → counter → purchased, with drop-off |
| `GET /api/conversion/hourly` | footfall vs transactions per hour → hourly conversion |
| `GET /api/sales/breakdowns` | transactions by department / brand / salesperson |
| `GET /api/events` | structured CCTV events (filterable) |
| `GET /api/zones` | live zone occupancy + dwell |
| `GET /api/alerts` | anomaly alerts (crowding / dwell / after-hours) |
| `GET /api/health` | dependency status |

Sample `/metrics` (with the provided Brigade Bangalore sales + seeded footfall):
```json
{ "store_name":"Brigade_Bangalore","date":"10-04-2026",
  "footfall":294,"transactions":24,"unique_customers":21,
  "net_revenue":34831.74,"conversion_rate_pct":8.16,"avg_basket_value":1451.32 }
```

---

## 🏗️ Architecture (short)

```
CCTV ─▶ YOLOv8 ─▶ ByteTrack ─▶ event logic (zones, door line, dwell)
                                    │
              events.jsonl ◀────────┼────────▶ SQLite (events/tracks/alerts)
              (replayable log)      │                    │
POS sales CSV ─▶ SalesData ─────────┴────▶ Conversion engine ─▶ FastAPI ─▶ dashboard
```

Full details + diagram: [`DESIGN.md`](DESIGN.md). Decisions & trade-offs: [`CHOICES.md`](CHOICES.md).

---

## 🧠 What it handles (edge cases)
- **Re-entry / line jitter** → session-based counting on distinct `track_id`s (no double count).
- **Occlusion** → ByteTrack `track_buffer`.
- **Group entry** → per-person tracks.
- **Missing sales CSV** → API degrades gracefully (`sales_available=false`).
- **No hardcoding** → every metric recomputed from inputs (passes integrity check).

## 🧪 Tests
```bash
pytest -q      # 13 passed: event logic + anomalies + conversion/funnel math
```

## 📂 Layout
```
backend/    FastAPI apps (main_lite=SQLite default, main=Postgres), sales + conversion logic
pipeline/   YOLOv8 + ByteTrack producer, zones (real store layout), event logic
consumer/   Redis Streams consumer + anomaly engine (full stack)
frontend/   conversion dashboard (HTML/CSS/JS + Chart.js)
scripts/    seed_lite, ingest_jsonl, sample video, init_db
tests/      unit tests
docs/       EVENT_SCHEMA, API, AI_ENGINEERING, EXECUTION_PLAN
DESIGN.md   CHOICES.md   (required by acceptance gate)
docker-compose.yml        (lite, default)   docker-compose.full.yml (Postgres+Redis)
```

## 🚀 Two deployment profiles
- **Lite** (default): SQLite + `events.jsonl`, tiny image, `docker compose up`.
- **Full** (scale story): Postgres + Redis Streams + consumer:
  `docker compose -f docker-compose.full.yml up --build`.

> ⚠️ Per challenge rules, **datasets and video files are gitignored** — never committed.

## ☁️ Online Deployment (Render)

This project is configured for deployment on **Render** (free tier).

### Build & Startup Configuration
- **Build Command**: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt`
- **Start Command**: `uvicorn backend.main_lite:app --host 0.0.0.0 --port $PORT`

### Environment Variables
- `PORT`: `8000` (automatically set by Render)
