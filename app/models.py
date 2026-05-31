"""
Pydantic schemas and SQLAlchemy ORM models for Store Intelligence API.
"""
from __future__ import annotations
from typing import Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import uuid

from sqlalchemy import Column, String, Boolean, Float, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from database import Base


# ─────────────────────────────────────────────
# SQLAlchemy ORM Models
# ─────────────────────────────────────────────

class EventORM(Base):
    __tablename__ = "events"

    event_id     = Column(String, primary_key=True)
    store_id     = Column(String, nullable=False, index=True)
    camera_id    = Column(String, nullable=False)
    visitor_id   = Column(String, nullable=False, index=True)
    event_type   = Column(String, nullable=False, index=True)
    timestamp    = Column(DateTime(timezone=True), nullable=False, index=True)
    zone_id      = Column(String, nullable=True)
    dwell_ms     = Column(Integer, default=0)
    is_staff     = Column(Boolean, default=False, index=True)
    confidence   = Column(Float, nullable=False)
    queue_depth  = Column(Integer, nullable=True)
    sku_zone     = Column(String, nullable=True)
    session_seq  = Column(Integer, nullable=True)
    raw_metadata = Column(JSONB, nullable=True)
    ingested_at  = Column(DateTime(timezone=True))


class POSTransactionORM(Base):
    __tablename__ = "pos_transactions"

    order_id          = Column(String, primary_key=True)
    store_id          = Column(String, nullable=False, index=True)
    transaction_time  = Column(DateTime(timezone=True), nullable=False, index=True)
    basket_value      = Column(Float, default=0)
    customer_number   = Column(String, nullable=True)
    salesperson_id    = Column(String, nullable=True)


# ─────────────────────────────────────────────
# Pydantic Schemas (API request/response)
# ─────────────────────────────────────────────

VALID_EVENT_TYPES = {
    "ENTRY", "EXIT", "ZONE_ENTER", "ZONE_EXIT", "ZONE_DWELL",
    "BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON", "REENTRY"
}


class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone:    Optional[str] = None
    session_seq: Optional[int] = None

    model_config = {"extra": "allow"}


class EventSchema(BaseModel):
    event_id:   str = Field(default_factory=lambda: str(uuid.uuid4()))
    store_id:   str
    camera_id:  str
    visitor_id: str
    event_type: str
    timestamp:  str
    zone_id:    Optional[str] = None
    dwell_ms:   int = 0
    is_staff:   bool = False
    confidence: float = Field(..., ge=0.0, le=1.0)
    metadata:   Optional[EventMetadata] = None

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v):
        if v not in VALID_EVENT_TYPES:
            raise ValueError(f"Unknown event_type: {v}. Must be one of {VALID_EVENT_TYPES}")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v):
        return round(float(v), 4)


class IngestRequest(BaseModel):
    events: list[EventSchema]


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    errors:   list[dict[str, Any]] = []


class ZoneDwellStat(BaseModel):
    zone_id:      str
    avg_dwell_ms: float
    visit_count:  int


class MetricsResponse(BaseModel):
    store_id:           str
    window:             str = "today"
    unique_visitors:    int
    conversion_rate:    float
    avg_dwell_per_zone: dict[str, float]
    queue_depth:        int
    abandonment_rate:   float
    computed_at:        str


class FunnelStage(BaseModel):
    stage:        str
    sessions:     int
    drop_off_pct: float


class FunnelResponse(BaseModel):
    store_id: str
    funnel:   list[FunnelStage]


class HeatmapZone(BaseModel):
    zone_id:      str
    visit_freq:   float        # normalised 0-100
    avg_dwell_ms: float


class HeatmapResponse(BaseModel):
    store_id:           str
    zones:              list[HeatmapZone]
    data_confidence:    str   # "HIGH" | "LOW"
    normalisation_base: int


class Anomaly(BaseModel):
    type:             str
    severity:         str   # INFO | WARN | CRITICAL
    detail:           str
    suggested_action: str
    zone_id:          Optional[str] = None
    detected_at:      str


class AnomaliesResponse(BaseModel):
    store_id:  str
    anomalies: list[Anomaly]


class StoreHealth(BaseModel):
    store_id:          str
    last_event_time:   Optional[str]
    is_stale:          bool
    seconds_since_last: Optional[float]


class HealthResponse(BaseModel):
    status:               str
    db_status:            str
    uptime_seconds:       float
    stores:               list[StoreHealth]
    stale_feeds:          list[str]
    checked_at:           str
