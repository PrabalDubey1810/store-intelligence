"""
GET /stores/{store_id}/funnel
Conversion funnel: Entry → Zone Visit → Billing Queue → Purchase.
Session is the unit — re-entries must NOT double-count.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import structlog

from database import get_db
from models import FunnelResponse, FunnelStage
from metrics import _compute_conversion_rate, BILLING_ZONES

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/stores/{store_id}/funnel", response_model=FunnelResponse)
def get_funnel(store_id: str, db: Session = Depends(get_db)):
    """
    Funnel stages based on sessions (unique visitor_id), not raw events.
    REENTRY events are NOT counted as a new session — same visitor_id is deduped.
    """

    # Stage 1: Unique customers who entered (ENTRY events, staff excluded)
    # Use DISTINCT visitor_id so re-entries don't double count
    entry_sessions = db.execute(text("""
        SELECT COUNT(DISTINCT visitor_id)
        FROM events
        WHERE store_id = :store_id
          AND event_type = 'ENTRY'
          AND is_staff = false
    """), {"store_id": store_id}).scalar() or 0

    # Stage 2: Visitors who entered at least one named zone (not just entry corridor)
    zone_sessions = db.execute(text("""
        SELECT COUNT(DISTINCT visitor_id)
        FROM events
        WHERE store_id = :store_id
          AND event_type IN ('ZONE_ENTER', 'ZONE_DWELL')
          AND zone_id IS NOT NULL
          AND is_staff = false
    """), {"store_id": store_id}).scalar() or 0

    # Stage 3: Visitors who joined billing queue
    billing_zone_list = ", ".join(f"'{z}'" for z in BILLING_ZONES)
    billing_sessions = db.execute(text(f"""
        SELECT COUNT(DISTINCT visitor_id)
        FROM events
        WHERE store_id = :store_id
          AND (
              event_type = 'BILLING_QUEUE_JOIN'
              OR (event_type IN ('ZONE_ENTER', 'ZONE_DWELL')
                  AND zone_id IN ({billing_zone_list}))
          )
          AND is_staff = false
    """), {"store_id": store_id}).scalar() or 0

    # Stage 4: Visitors who purchased (via POS correlation)
    total_visitors = entry_sessions
    conversion_rate = _compute_conversion_rate(store_id, db, total_visitors)
    purchase_sessions = round(total_visitors * conversion_rate)

    def drop_off(current: int, previous: int) -> float:
        if previous == 0:
            return 0.0
        return round((1 - current / previous) * 100, 1)

    stages = [
        FunnelStage(
            stage="entry",
            sessions=entry_sessions,
            drop_off_pct=0.0,
        ),
        FunnelStage(
            stage="zone_visit",
            sessions=zone_sessions,
            drop_off_pct=drop_off(zone_sessions, entry_sessions),
        ),
        FunnelStage(
            stage="billing_queue",
            sessions=billing_sessions,
            drop_off_pct=drop_off(billing_sessions, zone_sessions),
        ),
        FunnelStage(
            stage="purchase",
            sessions=purchase_sessions,
            drop_off_pct=drop_off(purchase_sessions, billing_sessions),
        ),
    ]

    return FunnelResponse(store_id=store_id, funnel=stages)
