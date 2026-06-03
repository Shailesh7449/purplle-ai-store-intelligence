# DESIGN.md — Store Intelligence System

> Required by the evaluation acceptance gate. This describes the system architecture
> and how raw CCTV footage + POS data become the **store conversion rate**.

## 1. Problem framing

The business question is simple but the signal is messy:

> **Of the people who walk into the Purplle store, what fraction actually buy something?**
> i.e. **Conversion rate = transactions ÷ footfall.**

- **Footfall** is *not* in any database — it must be **extracted from raw CCTV** by
  detecting and tracking people entering.
- **Transactions** come from the **POS sales export** (`data/sales/*.csv`) — one
  transaction = one unique `invoice_number`.

The system joins these two worlds and exposes the result through APIs + a dashboard.

## 2. Architecture

```
   CCTV video ─▶ YOLOv8 (person detect) ─▶ ByteTrack (track IDs)
                        │
                        ▼
              Event logic (zones, door line-crossing, dwell)
                        │
        events.jsonl  ◀─┼─▶  SQLite (events / tracks / alerts)
        (replayable     │
         event log)     ▼
                Anomaly engine (crowding / dwell / after-hours)

   POS sales CSV ─▶ SalesData (transactions, revenue, by hour/dept/brand)
                        │
                        ▼
   ┌────────────────────────────────────────────────────────┐
   │  Conversion engine: footfall (events) × sales (CSV)     │
   │   /metrics  → conversion rate, KPIs                      │
   │   /funnel   → entered → browsed → counter → purchased    │
   └────────────────────────────────────────────────────────┘
                        │ JSON
                        ▼
             FastAPI  +  HTML/Chart.js dashboard
```

Two run profiles, **same code**:
- **Lite** (default for dev/demo): SQLite + `events.jsonl`, run with plain Python.
- **Full** (for scale story): PostgreSQL + Redis Streams + a separate consumer,
  orchestrated by `docker compose up` (the acceptance-gate command).

## 3. Detection & tracking pipeline

- **Detector:** YOLOv8n (CPU-friendly, auto-downloads). Person class only.
- **Tracker:** ByteTrack via Ultralytics (`model.track(persist=True)`), giving each
  visitor a stable `track_id` across frames — the basis for *session-based* counting.
- **Footfall:** a normalised vertical **counting line** at the entrance; a track that
  crosses left→right is one entry. Counting **distinct track_ids** makes re-entry and
  line jitter collapse to a single visitor (no double counting).
- **Zones:** the store floor-plan mapped to normalised polygons — `entrance`,
  `shelf_top`, `foh`, `shelf_bottom`, `cash_counter` (see `pipeline/zones.py` /
  `data/store_layout.json`). Reaching `cash_counter` is the pre-purchase funnel stage.

## 4. Event schema

Flat, versioned, self-describing JSON (envelope + `payload`). Types: `track_started`,
`zone_enter`, `zone_exit`, `line_cross`, `occupancy_tick`, `track_ended`, plus alert
events. Full spec in `docs/EVENT_SCHEMA.md`. Events are written to **both** an
append-only `events.jsonl` (replayable log) and SQLite (queryable store), with
idempotent inserts keyed on `event_id`.

## 5. Business logic — conversion & funnel

- **`/metrics`** → footfall, transactions, unique customers, units, revenue (gross/net),
  **conversion rate**, average basket value.
- **`/funnel`** → session-based 4-stage funnel with stage-to-stage drop-off and overall
  conversion. Sessions are keyed by `track_id`, so a visitor counts once.
- **`/api/conversion/hourly`** → footfall vs transactions per hour → conversion by hour.
- **`/api/sales/breakdowns`** → conversion context by department / brand / salesperson.

All values are computed from the inputs at request time — **nothing is hardcoded**
(integrity requirement). Change the video or CSV and every number changes.

## 6. Edge cases handled

| Edge case | Handling |
|---|---|
| **Re-entry** (same person leaves & returns) | distinct `track_id` per session; footfall counts unique IDs |
| **Line jitter** (box wobble at the door) | sign-change crossing + distinct-ID counting |
| **Staff movement** | staff loiter in fixed zones (e.g. counter); documented filter hook in `event_logic` + future ReID note |
| **Group entry** | each person gets a track; group still counted per-person |
| **Occlusion** | ByteTrack `track_buffer` keeps IDs across short occlusions |
| **Missing sales CSV** | API degrades gracefully (`sales_available=false`), still serves footfall |

## 7. Observability & production

- Request logging middleware; `/api/health` reports SQLite + sales-CSV status.
- `docker compose up` brings up the full stack; lite mode runs with one `uvicorn`.
- Unit tests for event logic, anomaly rules, and conversion math (`tests/`).

## 8. Known limitations (honest)

- A single fixed camera can't see the whole store; zone polygons assume an
  entrance-facing view and should be tuned per camera via `store_layout.json`.
- Footfall↔sales are joined at aggregate (and hourly) level, not per-individual
  (no face ID) — the right privacy-respecting choice for a hiring demo.
- Detection accuracy is "good enough" by design (rubric: *not* a model contest).
