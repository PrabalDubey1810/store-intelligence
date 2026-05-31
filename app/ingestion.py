"""
POST /events/ingest — idempotent batch event ingestion.
Accepts up to 500 events. Validates, deduplicates, stores.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from pydantic import ValidationError
import structlog

from database import get_db
from models import EventSchema, IngestResponse

router = APIRouter()
log = structlog.get_logger(__name__)


@router.post("/events/ingest", response_model=IngestResponse)
async def ingest_events(request: Request, db: Session = Depends(get_db)):
    """
    Accepts batches of up to 500 events. Idempotent by event_id.
    Validates each event individually — bad events don't fail the whole batch.
    Returns partial success: {accepted: N, rejected: M, errors: [...]}.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid_json"})

    raw_events = body.get("events", [])[:500]  # Hard cap at 500
    accepted = 0
    errors = []

    for raw in raw_events:
        event_id = raw.get("event_id", "unknown")

        # Step 1: Validate individually — bad event → error, good event → DB
        try:
            event = EventSchema.model_validate(raw)
        except ValidationError as ve:
            errors.append({"event_id": event_id, "error": str(ve)})
            continue
        except Exception as e:
            errors.append({"event_id": event_id, "error": str(e)})
            continue

        # Step 2: Insert into DB (idempotent — ON CONFLICT DO NOTHING)
        try:
            meta = event.metadata or {}
            queue_depth = getattr(meta, "queue_depth", None) if meta else None
            sku_zone    = getattr(meta, "sku_zone", None) if meta else None
            session_seq = getattr(meta, "session_seq", None) if meta else None

            db.execute(
                text("""
                    INSERT INTO events (
                        event_id, store_id, camera_id, visitor_id,
                        event_type, timestamp, zone_id, dwell_ms,
                        is_staff, confidence, queue_depth, sku_zone,
                        session_seq, raw_metadata, ingested_at
                    ) VALUES (
                        :event_id, :store_id, :camera_id, :visitor_id,
                        :event_type, :timestamp, :zone_id, :dwell_ms,
                        :is_staff, :confidence, :queue_depth, :sku_zone,
                        :session_seq, :raw_metadata, :ingested_at
                    )
                    ON CONFLICT (event_id) DO NOTHING
                """),
                {
                    "event_id":    event.event_id,
                    "store_id":    event.store_id,
                    "camera_id":   event.camera_id,
                    "visitor_id":  event.visitor_id,
                    "event_type":  event.event_type,
                    "timestamp":   event.timestamp,
                    "zone_id":     event.zone_id,
                    "dwell_ms":    event.dwell_ms,
                    "is_staff":    event.is_staff,
                    "confidence":  event.confidence,
                    "queue_depth": queue_depth,
                    "sku_zone":    sku_zone,
                    "session_seq": session_seq,
                    "raw_metadata": None,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            accepted += 1

        except Exception as e:
            errors.append({"event_id": event.event_id, "error": str(e)})
            log.warning("event_ingest_db_error", error=str(e))

    db.commit()

    # Expose event_count for structured logging middleware
    request.state.event_count = accepted

    log.info("events_ingested",
             accepted=accepted,
             rejected=len(errors))

    return IngestResponse(accepted=accepted, rejected=len(errors), errors=errors)
