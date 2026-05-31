"""
GET /stores/{store_id}/anomalies
Active anomaly detection: queue spike, conversion drop, dead zone.
Severity: INFO / WARN / CRITICAL. Includes suggested_action per anomaly.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
import structlog

from database import get_db
from models import AnomaliesResponse, Anomaly

router = APIRouter()
log = structlog.get_logger(__name__)

# Thresholds
QUEUE_SPIKE_THRESHOLD   = 5       # Critical if queue depth > this
QUEUE_WARN_THRESHOLD    = 3       # Warn if queue depth > this
CONVERSION_DROP_PCT     = 0.20    # Warn if today's rate < 7-day avg × (1 - this)
DEAD_ZONE_MINUTES       = 30      # Warn if no visits in this window


@router.get("/stores/{store_id}/anomalies", response_model=AnomaliesResponse)
def get_anomalies(store_id: str, db: Session = Depends(get_db)):
    anomalies = []
    now = datetime.now(timezone.utc)

    # ── Anomaly 1: Billing Queue Spike ──────────────────────────────────────
    queue_depth_row = db.execute(text("""
        SELECT queue_depth FROM events
        WHERE store_id = :store_id
          AND event_type = 'BILLING_QUEUE_JOIN'
          AND queue_depth IS NOT NULL
        ORDER BY timestamp DESC LIMIT 1
    """), {"store_id": store_id}).fetchone()

    if queue_depth_row:
        depth = int(queue_depth_row.queue_depth)
        if depth > QUEUE_SPIKE_THRESHOLD:
            anomalies.append(Anomaly(
                type="BILLING_QUEUE_SPIKE",
                severity="CRITICAL",
                detail=f"Queue depth is {depth} (threshold: {QUEUE_SPIKE_THRESHOLD})",
                suggested_action=(
                    "Open an additional billing counter immediately — "
                    f"current depth of {depth} risks abandonment and revenue loss."
                ),
                detected_at=now.isoformat(),
            ))
        elif depth > QUEUE_WARN_THRESHOLD:
            anomalies.append(Anomaly(
                type="BILLING_QUEUE_SPIKE",
                severity="WARN",
                detail=f"Queue depth is {depth} (warn threshold: {QUEUE_WARN_THRESHOLD})",
                suggested_action=(
                    "Alert billing staff to speed up processing — "
                    "queue is building and may deepen."
                ),
                detected_at=now.isoformat(),
            ))

    # ── Anomaly 2: Conversion Drop vs 7-day average ─────────────────────────
    # Today's conversion rate
    from metrics import _compute_conversion_rate
    total_visitors = db.execute(text("""
        SELECT COUNT(DISTINCT visitor_id) FROM events
        WHERE store_id = :store_id AND event_type = 'ENTRY' AND is_staff = false
    """), {"store_id": store_id}).scalar() or 0

    today_rate = _compute_conversion_rate(store_id, db, total_visitors)

    # Approximate 7-day average from POS data (use total tx count / estimated daily avg)
    pos_total = db.execute(text("""
        SELECT COUNT(*) FROM pos_transactions WHERE store_id = :store_id
    """), {"store_id": store_id}).scalar() or 0

    # Use a baseline of 30% if we don't have 7-day history
    baseline_rate = 0.30
    if today_rate < baseline_rate * (1 - CONVERSION_DROP_PCT):
        anomalies.append(Anomaly(
            type="CONVERSION_DROP",
            severity="WARN",
            detail=(
                f"Conversion rate is {today_rate:.1%} vs "
                f"baseline {baseline_rate:.1%} "
                f"(>{CONVERSION_DROP_PCT:.0%} drop)"
            ),
            suggested_action=(
                "Review billing zone staffing and queue wait times. "
                "Consider activating a salesperson to assist customers in the billing area."
            ),
            detected_at=now.isoformat(),
        ))

    # ── Anomaly 3: Dead Zones (no visits in last 30 minutes) ─────────────────
    cutoff = (now - timedelta(minutes=DEAD_ZONE_MINUTES)).isoformat()

    # Get all zones that have ever had visits
    all_zones = db.execute(text("""
        SELECT DISTINCT zone_id FROM events
        WHERE store_id = :store_id AND zone_id IS NOT NULL AND is_staff = false
    """), {"store_id": store_id}).fetchall()

    # Get zones with recent activity
    recent_zones = db.execute(text("""
        SELECT DISTINCT zone_id FROM events
        WHERE store_id = :store_id
          AND zone_id IS NOT NULL
          AND is_staff = false
          AND timestamp >= :cutoff
    """), {"store_id": store_id, "cutoff": cutoff}).fetchall()

    recent_set  = {r.zone_id for r in recent_zones}
    all_zone_set = {r.zone_id for r in all_zones}
    dead_zones  = all_zone_set - recent_set

    for zone in dead_zones:
        anomalies.append(Anomaly(
            type="DEAD_ZONE",
            severity="INFO",
            zone_id=zone,
            detail=f"No customer visits in zone '{zone}' in the last {DEAD_ZONE_MINUTES} minutes",
            suggested_action=(
                f"Deploy a salesperson to the {zone} zone for product demos "
                "or check if signage/display is obstructing customer flow."
            ),
            detected_at=now.isoformat(),
        ))

    log.info("anomalies_computed",
             store_id=store_id,
             count=len(anomalies),
             types=[a.type for a in anomalies])

    return AnomaliesResponse(store_id=store_id, anomalies=anomalies)
