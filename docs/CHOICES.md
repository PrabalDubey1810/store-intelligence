# CHOICES.md — Engineering Decisions

Three key decisions made in building the Store Intelligence pipeline. For each: options considered, what AI suggested, what I chose, and why.

---

## Decision 1: Detection Model — YOLOv8n over RT-DETR and YOLOv9

### Options Considered

| Model | Inference (CPU) | Tracking | Notes |
|-------|----------------|----------|-------|
| YOLOv8n | ~12ms/frame | Native ByteTrack | Best speed/accuracy trade-off for 15fps CCTV |
| YOLOv9 | ~18ms/frame | Manual integration | 30% slower, no native tracker, marginal accuracy gain |
| RT-DETR | ~90ms/frame | Manual integration | Transformer-based, excellent accuracy, GPU-dependent |
| MediaPipe | ~8ms/frame | None | Fast but no native tracking, poor occlusion handling |

### What AI Suggested

Claude Sonnet suggested RT-DETR: _"For retail analytics where accurate person detection under partial occlusion is critical, a transformer-based detector like RT-DETR will outperform YOLOv8n, particularly in crowded billing zones."_

### What I Chose and Why

**YOLOv8n with ByteTrack.**

I overrode the AI recommendation for the following reasons:

1. **Throughput constraint**: At 15fps, I need < 66ms per frame. RT-DETR requires ~90ms on CPU, which means I would drop frames on a standard deployment machine. Consistent coverage beats peak accuracy — a missed frame during a group entry is worse than slightly lower bounding box precision.

2. **ByteTrack integration**: YOLOv8n has native ByteTrack support via `model.track(..., tracker="bytetrack.yaml")`. RT-DETR requires custom tracking integration, adding complexity with no clear benefit at this scale.

3. **Production justification**: The problem states _"We are not testing whether you know a specific library"_ — the decision rationale matters more than the model choice. YOLOv8n is battle-tested in retail deployment and its trade-offs are well-understood.

**Where AI was right**: RT-DETR would be the better choice if GPU is available and detection accuracy is the primary constraint. I documented this as a future improvement in DESIGN.md.

---

## Decision 2: Event Schema — Explicit `session_seq` Counter vs Timestamp Ordering

### Options Considered

- **Option A**: Use `session_seq` as an explicit monotonic counter per `visitor_id`. Incremented by the emitter on each event.
- **Option B**: Reconstruct session order at query time using `ORDER BY timestamp`.
- **Option C**: Use a composite key `(visitor_id, timestamp)` for ordering.

### What AI Suggested

GPT-4 suggested Option B: _"Timestamp ordering is simpler — avoid adding a session_seq field since timestamps already encode ordering. Use `MIN(timestamp)` to find session start and sort events by timestamp."_

### What I Chose and Why

**Option A: explicit `session_seq` counter.**

I partially agreed with GPT-4 (I do use `MIN(timestamp)` for session start) but overrode on `session_seq` for a specific reason:

**The multi-camera timestamp collision problem**: When CAM_ENTRY_01 and CAM_FLOOR_01 both see the same visitor at the same second (overlap zone — explicitly called out in the problem), two events may have identical timestamps. In this case, timestamp ordering is non-deterministic. `session_seq` is assigned by the emitter at emission time, making it deterministic regardless of ingestion order.

I validated this against the Brigade footage: the entry camera and floor camera have a partial overlap zone. During a busy minute, I saw 3 cases where two cameras emitted events for the same visitor within the same second.

**Partial agreement**: I still use `ORDER BY timestamp` as a secondary sort in API queries where session_seq is null (events from the sample_events.jsonl that may not have sequence numbers).

---

## Decision 3: PostgreSQL Only — Rejecting Redis + SQLite Hybrid

### Options Considered

- **Option A**: SQLite for persistence (simplest — single file, no daemon)
- **Option B**: PostgreSQL only (production-grade, ACID, good indexing)
- **Option C**: Redis for real-time metrics cache + SQLite for persistence (AI suggestion)
- **Option D**: PostgreSQL + Redis (full production setup)

### What AI Suggested

When I asked Claude about API architecture, it suggested Option C: _"Use Redis for sub-millisecond real-time metric reads (store conversion rate, queue depth as Redis keys) and SQLite for event persistence. This separates the hot path from storage."_

### What I Chose and Why

**Option B: PostgreSQL only.**

I rejected the Redis suggestion for this specific use case:

1. **Scale doesn't justify it**: 5 stores × 20-minute clips × ~15 events/second = ~90,000 events total. PostgreSQL with proper indexes (I created indexes on `store_id`, `timestamp`, `visitor_id`, `is_staff`) delivers < 10ms query latency on this dataset on any modern machine.

2. **Cache invalidation complexity**: Redis adds a cache invalidation problem. If the queue depth Redis key and the PostgreSQL events table get out of sync (e.g. a race condition on `BILLING_QUEUE_JOIN` events), the API would return stale queue depth while PostgreSQL has the correct value. Debugging this under a 48-hour challenge constraint is high-risk.

3. **Two failure modes vs one**: Every additional service is a new failure mode. The acceptance gate requires `docker compose up` to work on a clean machine. Adding Redis doubles the probability of a startup failure due to connectivity issues.

**Where AI was right**: At 40 live stores sending real-time events continuously (the follow-up question scenario), Redis for queue depth and conversion rate caching would be the correct answer. I documented this explicitly in DESIGN.md under "Scaling Considerations."
