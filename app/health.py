"""
GET /health — Service status, last event timestamp per store, STALE_FEED warning.
This is what an on-call engineer checks first.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
import time as _time
import structlog

from database import get_db, check_db_health
from models import HealthResponse, StoreHealth

router = APIRouter()
log = structlog.get_logger(__name__)

START_TIME = _time.time()
STALE_FEED_MINUTES = 10


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """
    Accurate health check — reads real last-event timestamps from DB.
    Reports STALE_FEED if any store has not received events in > 10 minutes.
    """
    now = datetime.now(timezone.utc)
    db_status_obj = check_db_health()
    db_status = db_status_obj["status"]

    # Get last event time per store
    store_rows = db.execute(text("""
        SELECT store_id, MAX(timestamp) as last_event
        FROM events
        GROUP BY store_id
    """)).fetchall()

    stores = []
    stale_feeds = []

    for row in store_rows:
        last_event = row.last_event
        if last_event and last_event.tzinfo is None:
            last_event = last_event.replace(tzinfo=timezone.utc)

        if last_event:
            diff = (now - last_event).total_seconds()
            is_stale = diff > (STALE_FEED_MINUTES * 60)
        else:
            diff = None
            is_stale = True

        if is_stale:
            stale_feeds.append(row.store_id)

        stores.append(StoreHealth(
            store_id=row.store_id,
            last_event_time=last_event.isoformat() if last_event else None,
            is_stale=is_stale,
            seconds_since_last=round(diff, 1) if diff is not None else None,
        ))

    # If no events yet, report known stores from stores table
    if not stores:
        known = db.execute(text("SELECT store_id FROM stores")).fetchall()
        for row in known:
            stores.append(StoreHealth(
                store_id=row.store_id,
                last_event_time=None,
                is_stale=True,
                seconds_since_last=None,
            ))
            stale_feeds.append(row.store_id)

    overall_status = "ok" if db_status == "connected" else "degraded"

    return HealthResponse(
        status=overall_status,
        db_status=db_status,
        uptime_seconds=round(_time.time() - START_TIME, 2),
        stores=stores,
        stale_feeds=stale_feeds,
        checked_at=now.isoformat(),
    )
