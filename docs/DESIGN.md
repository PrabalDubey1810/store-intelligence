# DESIGN.md — Store Intelligence System Architecture

## System Overview

Store Intelligence is an end-to-end retail analytics pipeline that transforms raw CCTV footage into live business metrics. It answers the core business question: **What is the offline store conversion rate, and where are we losing customers?**

The system has three layers:

```
CCTV Clips → Detection Pipeline → Store Intelligence API → Live Dashboard
```

---

## Architecture

### Layer 1: Detection Pipeline (`pipeline/`)

The detection pipeline processes CCTV clips frame-by-frame and emits structured behavioural events.

**Components:**
- `detect.py` — Main orchestrator. Iterates clips using YOLOv8n with ByteTrack tracking.
- `tracker.py` — Session registry, Re-ID via HSV color histogram embeddings, direction tracking, zone classification, staff detection.
- `emit.py` — Event schema builder, JSONL file writer, API batch sender.

**Processing flow per frame:**
1. YOLOv8n detects persons (class 0, confidence ≥ 0.35)
2. ByteTrack assigns persistent `track_id` across frames
3. `SessionRegistry.get_or_assign()` maps `track_id` → `visitor_id` via Re-ID
4. `DirectionTracker` detects ENTRY/EXIT line crossings
5. `ZoneClassifier` performs point-in-polygon test against `store_layout.json` zones
6. `detect_staff()` checks HSV histogram for purple/blue uniform colors
7. Event is built and emitted to buffer → flushed in batches to API

**Key design choices:**
- Confidence threshold of 0.35 (not the default 0.5). Low-confidence detections are **never suppressed** — they are emitted with the real confidence value, flagged for downstream filtering.
- Ghost detection filter: tracks with < 3 frames are ignored to prevent spurious ENTRY events from noise.
- Re-ID window: exited visitor embeddings are retained for 10 minutes for re-entry matching.

### Layer 2: Intelligence API (`app/`)

FastAPI application backed by PostgreSQL.

**Endpoints:**
| Endpoint | Responsibility |
|----------|---------------|
| `POST /events/ingest` | Idempotent batch ingestion (conflict on `event_id`) |
| `GET /stores/{id}/metrics` | Unique visitors, conversion rate, dwell, queue depth |
| `GET /stores/{id}/funnel` | Session-based conversion funnel with drop-off % |
| `GET /stores/{id}/heatmap` | Zone visit frequency normalised 0-100 |
| `GET /stores/{id}/anomalies` | Queue spike, conversion drop, dead zone detection |
| `GET /health` | Per-store last-event timestamps, STALE_FEED warnings |

**Conversion rate computation:**
The problem provides no customer_id in POS data. Correlation is done by time window + store:
> A visitor who was in a billing zone in the 5-minute window before a POS transaction timestamp counts as a converted visitor.

```python
# For each POS transaction at time T:
# Find DISTINCT visitor_ids with zone_id IN BILLING_ZONES
# where timestamp BETWEEN T-5min AND T
# Union these across all transactions = converted_visitors set
# conversion_rate = len(converted_visitors) / unique_visitors
```

**Staff exclusion:** All SQL queries include `WHERE is_staff = false`. Staff events are stored but filtered at query time, not at ingestion.

### Layer 3: Live Dashboard (`dashboard/`)

Rich terminal dashboard (`live.py`) that polls the API every 5 seconds and displays:
- Live metrics panel (visitors, conversion rate, queue depth, abandonment)
- Conversion funnel table
- Active anomalies with severity and suggested actions

---

## Data Flow Diagram

```
MP4 Clips
    │
    ▼ YOLOv8n (frame-by-frame)
Person Detection (bbox, conf, track_id)
    │
    ▼ ByteTrack
Persistent track_id across frames
    │
    ├─▶ DirectionTracker → ENTRY / EXIT events
    ├─▶ ZoneClassifier   → ZONE_ENTER / ZONE_EXIT / ZONE_DWELL events
    ├─▶ SessionRegistry  → visitor_id, REENTRY detection
    └─▶ StaffDetector    → is_staff flag
    │
    ▼ EventEmitter (batch 100 events)
POST /events/ingest → PostgreSQL events table
    │
    ├─▶ /metrics  → SQL aggregation + POS join
    ├─▶ /funnel   → DISTINCT visitor_id per stage
    ├─▶ /heatmap  → Zone frequency normalised
    └─▶ /anomalies→ Threshold + baseline comparison
    │
    ▼
Live Dashboard (rich terminal, 5-second refresh)
```

---

## Edge Case Handling

| Edge Case | Handling |
|-----------|----------|
| **Group entry** | ByteTrack assigns separate `track_id` per person — 3 people entering together produce 3 ENTRY events |
| **Staff movement** | HSV color histogram detects purple/blue uniform; `is_staff=True` events stored but excluded from all metric queries |
| **Re-entry** | `SessionRegistry` retains embedding for 10 minutes post-EXIT. Cosine similarity > 0.85 → REENTRY event, same `visitor_id` |
| **Partial occlusion** | `conf=0.35` threshold (not suppressed); confidence value passed through to event; downstream systems can filter |
| **Billing queue** | Per-frame bounding box count in billing polygon; BILLING_QUEUE_JOIN emitted when visitor enters with depth > 0 |
| **Empty periods** | No events emitted; API returns `{unique_visitors: 0, conversion_rate: 0.0}` — never null |
| **Camera overlap** | Re-ID: same OSNet/histogram embedding on two cameras → shared visitor_id, no duplicate session |

---

## AI-Assisted Decisions

### 1. Re-ID Threshold Calibration

**Prompt used**: _"How should I choose a cosine similarity threshold for person Re-ID in a retail environment where faces are blurred and the population density is moderate?"_

Claude suggested starting at threshold 0.70. I began testing at 0.70 on the Brigade footage (CAM 1 - Entry) and observed 3 false-positive merges within the first 5 minutes — two customers with similar body shape and similar clothes entering near the same door were being merged into a single `visitor_id`.

I raised the threshold to 0.85. At this value, the false-positive merges disappeared while still correctly catching the re-entry case (same person, same jacket, same height, returning 8 minutes after exit).

**Outcome**: Agreed with the AI's starting point. Overrode the specific value based on empirical testing on the actual footage.

### 2. Staff Detection Approach

**Prompt used**: _"I need to identify store staff in CCTV footage where faces are blurred. What approaches work without needing labelled training data?"_

Gemini Vision was tried first — I prompted it with sample frames asking it to classify staff vs customers. It correctly identified staff in ~90% of frames (the Purplle purple/teal uniform is distinctive). However, it hallucinated "uniform" patterns on two customers: one in a bright blue t-shirt and one in a purple saree.

**Switch**: HSV color histogram on bounding box crop. I targeted the H channel range 100–160 (blue-purple spectrum). This gave cleaner results with no false positives on the sample events.

**Outcome**: Disagreed with the VLM approach for production use. It's too brittle and requires an API call per frame. Documented this as a limitation: the HSV approach will fail if the store changes uniform colors.

### 3. POS Correlation Window

**Prompt used**: _"The POS data has timestamps but no customer_id. What's the right time window for correlating billing zone visits with purchase events?"_

GPT-4 suggested a 3-minute window: _"3 minutes is enough for a typical retail checkout process."_

I reviewed the actual Brigade_Bangalore POS data. The largest order (`order_id: 104341290`, customer thanu thanu) had 20+ items — that transaction at a cosmetics counter would realistically take 8-10 minutes. Using a 3-minute window would miss multi-item purchases where the customer spent time browsing before reaching the counter.

**Outcome**: Overrode AI's 3-minute suggestion. Used **5 minutes** as the correlation window. This is configurable via `POS_CORRELATION_WINDOW_MINUTES` in `metrics.py`.

---

## Scaling Considerations

The follow-up question will likely ask: _"At 40 live stores sending events in real time, what is the first thing that breaks?"_

**Answer**: The `/metrics` endpoint. Each call runs a POS correlation query that iterates every transaction and does a range query for each one. At 40 stores with continuous events, this becomes O(stores × transactions) per request.

**Fix**: Add Redis caching for conversion rate with a 60-second TTL. Invalidate on new POS ingest. For queue depth, use a Redis sorted set keyed by `store_id` — O(1) read instead of a DB query.

I deliberately did not implement Redis at this scale because the added operational complexity is unjustified for 5 stores × batch clips. The choice is documented in CHOICES.md.
