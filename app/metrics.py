"""
GET /stores/{store_id}/metrics
Real-time store metrics: unique visitors, conversion rate, avg dwell per zone,
queue depth, abandonment rate. Excludes is_staff=true events.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
import structlog

from database import get_db
from models import MetricsResponse

router = APIRouter()
log = structlog.get_logger(__name__)

# Zone IDs that count as billing/conversion zones for POS time-window correlation.
# Updated to match physical store signage in store_layout.json v2.
# Previously: {"BILLING", "BILLING_COUNTER", "CHECKOUT", ...}
BILLING_ZONES = {"CASH_COUNTER"}
POS_CORRELATION_WINDOW_MINUTES = 5



@router.get("/stores/{store_id}/metrics", response_model=MetricsResponse)
def get_metrics(store_id: str, db: Session = Depends(get_db)):
    """
    Real-time store metrics for today's session window.
    Conversion: visitors in billing zone within 5 min before a POS transaction.
    """

    # 1. Unique customer visitors (ENTRY events, staff excluded)
    unique_visitors = db.execute(text("""
        SELECT COUNT(DISTINCT visitor_id)
        FROM events
        WHERE store_id = :store_id
          AND event_type = 'ENTRY'
          AND is_staff = false
    """), {"store_id": store_id}).scalar() or 0

    # 2. Average dwell per zone (staff excluded)
    zone_rows = db.execute(text("""
        SELECT zone_id, AVG(dwell_ms) as avg_dwell, COUNT(*) as cnt
        FROM events
        WHERE store_id = :store_id
          AND zone_id IS NOT NULL
          AND is_staff = false
          AND dwell_ms > 0
        GROUP BY zone_id
        ORDER BY cnt DESC
    """), {"store_id": store_id}).fetchall()

    avg_dwell_per_zone = {
        row.zone_id: round(float(row.avg_dwell), 2)
        for row in zone_rows if row.zone_id
    }

    # 3. Current queue depth (most recent BILLING_QUEUE_JOIN event)
    queue_depth_row = db.execute(text("""
        SELECT queue_depth
        FROM events
        WHERE store_id = :store_id
          AND event_type = 'BILLING_QUEUE_JOIN'
          AND queue_depth IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 1
    """), {"store_id": store_id}).fetchone()
    queue_depth = int(queue_depth_row.queue_depth) if queue_depth_row else 0

    # 4. Abandonment rate
    queue_joins = db.execute(text("""
        SELECT COUNT(DISTINCT visitor_id) FROM events
        WHERE store_id = :store_id AND event_type = 'BILLING_QUEUE_JOIN'
          AND is_staff = false
    """), {"store_id": store_id}).scalar() or 0

    queue_abandons = db.execute(text("""
        SELECT COUNT(DISTINCT visitor_id) FROM events
        WHERE store_id = :store_id AND event_type = 'BILLING_QUEUE_ABANDON'
          AND is_staff = false
    """), {"store_id": store_id}).scalar() or 0

    abandonment_rate = round(queue_abandons / queue_joins, 4) if queue_joins > 0 else 0.0

    # 5. Conversion rate via POS correlation
    conversion_rate = _compute_conversion_rate(store_id, db, unique_visitors)

    return MetricsResponse(
        store_id=store_id,
        window="today",
        unique_visitors=unique_visitors,
        conversion_rate=conversion_rate,
        avg_dwell_per_zone=avg_dwell_per_zone,
        queue_depth=queue_depth,
        abandonment_rate=abandonment_rate,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


def _compute_conversion_rate(store_id: str, db: Session, total_visitors: int) -> float:
    """
    Conversion = visitors who were in billing zone within 5 min before any POS tx.
    Correlation done by time window + store_id (no customer_id in POS data).
    """
    if total_visitors == 0:
        return 0.0

    pos_times = db.execute(text("""
        SELECT transaction_time FROM pos_transactions
        WHERE store_id = :store_id
        ORDER BY transaction_time
    """), {"store_id": store_id}).fetchall()

    if not pos_times:
        return 0.0

    converted = set()

    for row in pos_times:
        raw = row.transaction_time
        # SQLite returns strings; PostgreSQL returns datetime objects
        if isinstance(raw, str):
            try:
                txn_time = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except Exception:
                continue
        else:
            txn_time = raw
        if txn_time.tzinfo is None:
            txn_time = txn_time.replace(tzinfo=timezone.utc)
        window_start = txn_time - timedelta(minutes=POS_CORRELATION_WINDOW_MINUTES)

        billing_zone_list = ", ".join(f"'{z}'" for z in BILLING_ZONES)
        billing_visitors = db.execute(text(f"""
            SELECT DISTINCT visitor_id
            FROM events
            WHERE store_id = :store_id
              AND zone_id IN ({billing_zone_list})
              AND timestamp >= :window_start
              AND timestamp <= :txn_time
              AND is_staff = false
        """), {
            "store_id":     store_id,
            "window_start": window_start.isoformat(),
            "txn_time":     txn_time.isoformat(),
        }).fetchall()

        for v in billing_visitors:
            converted.add(v.visitor_id)

    return round(len(converted) / total_visitors, 4) if total_visitors > 0 else 0.0
