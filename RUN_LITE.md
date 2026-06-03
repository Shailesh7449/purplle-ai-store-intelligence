# ⚡ Lite Mode — run with just Python (no Docker, no Postgres, no Redis)

Built for a laptop with limited disk space and a tight deadline. Stack:

```
YOLOv8n → ByteTrack → events.jsonl → SQLite → FastAPI → dashboard
```

SQLite is part of Python's standard library, so there is **nothing extra to install**
for storage. The `events.jsonl` file is your replayable event log (same idea as a
Kafka topic / Redis stream — just a file).

---

## 0) One-time setup

```powershell
cd C:\Users\DELL\Downloads\store-intelligence

python -m venv .venv
.\.venv\Scripts\activate

# Install CPU-only PyTorch FIRST (avoids ~5 GB of NVIDIA/CUDA libraries):
pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cpu

# Then the lite requirements:
pip install -r requirements-lite.txt
```

> Total install is ~2 GB (mostly CPU torch + opencv). Fits comfortably in 10 GB.

---

## 1) Instant demo — NO video / NO YOLO needed ✅

Great for checking everything works (and for demoing while the dataset downloads):

```powershell
python scripts\seed_lite.py
uvicorn backend.main_lite:app
```
Open **http://localhost:8000**  →  KPIs, zones, footfall chart, alerts, event feed.
API docs at **http://localhost:8000/docs**.

---

## 2) Real run — on actual CCTV footage 🎥

Put a clip at `data\videos\store.mp4` (do **not** commit it), then:

```powershell
# Terminal A — process the video (writes events.jsonl + SQLite)
python -m pipeline.run_lite --source data\videos\store.mp4

# Terminal B — serve the API + dashboard
uvicorn backend.main_lite:app
```
YOLOv8n auto-downloads (~6 MB) on first run. Use `--source 0` for a webcam.

---

## 3) Replay the event log into the DB (optional)

Shows that `events.jsonl` is a replayable stream:

```powershell
python scripts\ingest_jsonl.py data\output\events.jsonl
```

---

## 4) Tests

```powershell
pip install pytest
pytest -q          # 9 passed
```

---

## What changed vs. the full architecture?

| Full (in repo) | Lite (this) | Why |
|---|---|---|
| PostgreSQL | **SQLite** | stdlib, zero install, single file |
| Redis Streams | **events.jsonl** | a file IS a replayable log |
| separate consumer service | folded into `run_lite.py` | one process, less to run |
| WebSocket live push | REST polling (4s) | fewer deps, plenty for a demo |
| Docker Compose | **not needed** | run directly with Python |

The full Postgres/Redis/Docker implementation is **still in the repo** (`backend/db.py`,
`backend/main.py`, `consumer/`, `docker-compose.yml`) — it's your "scales to production"
story for the writeup. Lite mode is what you actually run and demo. This contrast
(*"I built it to scale, and I also shipped a lean version that runs anywhere"*) is a
strong talking point. See `docs/DECISIONS.md`.
