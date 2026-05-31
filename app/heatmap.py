"""
GET /stores/{store_id}/heatmap
Zone visit frequency + avg dwell, normalised 0-100.
Includes data_confidence flag if fewer than 20 sessions.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models import HeatmapResponse, HeatmapZone

router = APIRouter()
LOW_CONFIDENCE_THRESHOLD = 20


@router.get("/stores/{store_id}/heatmap", response_model=HeatmapResponse)
def get_heatmap(store_id: str, db: Session = Depends(get_db)):
    """
    Zone heatmap: visit frequency normalised to 0-100. 
    Excludes staff, excludes null zones (entry/exit threshold).
    """

    rows = db.execute(text("""
        SELECT
            zone_id,
            COUNT(DISTINCT visitor_id)  AS unique_visitors,
            AVG(dwell_ms)               AS avg_dwell
        FROM events
        WHERE store_id = :store_id
          AND zone_id IS NOT NULL
          AND is_staff = false
          AND event_type IN ('ZONE_ENTER', 'ZONE_DWELL')
        GROUP BY zone_id
        ORDER BY unique_visitors DESC
    """), {"store_id": store_id}).fetchall()

    if not rows:
        return HeatmapResponse(
            store_id=store_id,
            zones=[],
            data_confidence="LOW",
            normalisation_base=0,
        )

    max_visitors = rows[0].unique_visitors or 1
    total_sessions = sum(r.unique_visitors for r in rows)

    zones = [
        HeatmapZone(
            zone_id=row.zone_id,
            visit_freq=round((row.unique_visitors / max_visitors) * 100, 1),
            avg_dwell_ms=round(float(row.avg_dwell or 0), 2),
        )
        for row in rows
    ]

    confidence = "HIGH" if total_sessions >= LOW_CONFIDENCE_THRESHOLD else "LOW"

    return HeatmapResponse(
        store_id=store_id,
        zones=zones,
        data_confidence=confidence,
        normalisation_base=total_sessions,
    )
