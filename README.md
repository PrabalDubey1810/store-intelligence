# Store Intelligence API

End-to-end retail analytics pipeline: CCTV footage → structured events → live store metrics.

Built for Purplle Tech Challenge 2026 — Brigade Road, Bangalore (Store: ST1008).

---

## Quick Start (5 commands)

```bash
# 1. Clone and enter
git clone <your-repo-url>
cd store-intelligence

# 2. Copy POS data
cp /path/to/pos_transactions.csv data/pos_transactions.csv

# 3. Start the API and database
docker compose up -d

# 4. Process CCTV clips (generates events.jsonl)
python pipeline/detect.py \
  --clips-dir "CCTV Footage/" \
  --store-id ST1008 \
  --layout data/store_layout.json \
  --output data/events.jsonl \
  --api http://localhost:8000

# 5. View live dashboard
python dashboard/live.py --store ST1008 --api http://localhost:8000
```

API is available at: http://localhost:8000  
Interactive docs: http://localhost:8000/docs

---

## What's Built

| Component | Description |
|-----------|-------------|
| `pipeline/detect.py` | YOLOv8n + ByteTrack detection on CCTV clips |
| `pipeline/tracker.py` | Re-ID, direction detection, zone classification, staff detection |
| `pipeline/emit.py` | Event emitter — JSONL file + API batch sender |
| `app/main.py` | FastAPI application with structured logging |
| `app/metrics.py` | `GET /stores/{id}/metrics` — conversion rate, dwell, queue |
| `app/funnel.py` | `GET /stores/{id}/funnel` — session-based conversion funnel |
| `app/heatmap.py` | `GET /stores/{id}/heatmap` — zone visit frequency 0-100 |
| `app/anomalies.py` | `GET /stores/{id}/anomalies` — queue spike, conversion drop, dead zone |
| `app/health.py` | `GET /health` — per-store staleness and DB status |
| `dashboard/live.py` | Rich terminal live dashboard (5-second refresh) |

---

## API Endpoints

```
POST /events/ingest              Ingest up to 500 events (idempotent by event_id)
GET  /stores/{id}/metrics        Unique visitors, conversion rate, avg dwell, queue depth
GET  /stores/{id}/funnel         Entry → Zone → Billing → Purchase funnel
GET  /stores/{id}/heatmap        Zone visit heatmap, normalised 0-100
GET  /stores/{id}/anomalies      Active anomalies with severity + suggested_action
GET  /health                     DB status + per-store last event timestamps
```

**Example:**
```bash
curl http://localhost:8000/stores/ST1008/metrics
curl http://localhost:8000/stores/ST1008/funnel
curl http://localhost:8000/stores/ST1008/anomalies
curl http://localhost:8000/health
```

---

## Running Tests

```bash
cd store-intelligence
pip install pytest pytest-cov httpx
pytest tests/ -v --cov=app --cov-report=term-missing
```

Expected coverage: > 70%

---

## Replaying Pre-Processed Events

If you've already run `detect.py` and have `events.jsonl`:

```bash
python pipeline/emit.py --input data/events.jsonl --api http://localhost:8000
```

---

## Project Structure

```
store-intelligence/
├── pipeline/
│   ├── detect.py          # YOLOv8n + ByteTrack main detection script
│   ├── tracker.py         # Re-ID, zone classifier, staff detection
│   └── emit.py            # Event schema + API emitter
├── app/
│   ├── main.py            # FastAPI entrypoint + middleware
│   ├── models.py          # Pydantic schemas + SQLAlchemy ORM
│   ├── database.py        # DB connection
│   ├── ingestion.py       # POST /events/ingest
│   ├── metrics.py         # GET /stores/{id}/metrics
│   ├── funnel.py          # GET /stores/{id}/funnel
│   ├── heatmap.py         # GET /stores/{id}/heatmap
│   ├── anomalies.py       # GET /stores/{id}/anomalies
│   ├── health.py          # GET /health
│   ├── pos_loader.py      # POS CSV loader (runs at startup)
│   ├── init.sql           # Database schema
│   ├── requirements.txt
│   └── Dockerfile
├── dashboard/
│   ├── live.py            # Rich terminal dashboard
│   └── Dockerfile
├── tests/
│   ├── conftest.py        # Fixtures (SQLite in-memory test DB)
│   ├── test_ingestion.py
│   ├── test_metrics.py
│   ├── test_anomalies.py
│   └── test_funnel.py
├── docs/
│   ├── DESIGN.md          # Architecture + AI-assisted decisions
│   └── CHOICES.md         # 3 engineering decisions with full reasoning
├── data/                  # Mount point for POS CSV and events.jsonl
└── docker-compose.yml
```

---

## Architecture Summary

```
CCTV MP4 Clips
      │ YOLOv8n + ByteTrack
      ▼
Detection Pipeline (Python)
  ├── Per-person track → visitor_id (Re-ID via HSV embeddings)
  ├── Entry/Exit line crossing → ENTRY/EXIT events
  ├── Zone polygon test → ZONE_ENTER/EXIT/DWELL events
  └── HSV histogram → is_staff flag
      │ POST /events/ingest (batches)
      ▼
FastAPI + PostgreSQL
  ├── Conversion rate via POS time-window correlation
  ├── Session-based funnel (DISTINCT visitor_id per stage)
  ├── Anomaly detection (queue spike, conversion drop, dead zone)
  └── Structured logging (trace_id, latency_ms, store_id)
      │ HTTP polling
      ▼
Rich Terminal Dashboard (5s refresh)
```

See `docs/DESIGN.md` for full architecture documentation.  
See `docs/CHOICES.md` for engineering decision rationale.
