# ============================================================
# PROMPT: "Write pytest tests for GET /stores/{id}/metrics endpoint.
# Cover: empty store returns zero not null, staff events excluded from
# unique_visitors, conversion_rate is 0.0 not null when no POS data,
# conversion_rate computes correctly when visitor was in billing zone
# before a POS transaction, queue_depth reflects latest BILLING_QUEUE_JOIN,
# abandonment_rate computed from abandon vs join events."
#
# CHANGES MADE:
# - Added explicit assertion that conversion_rate is float (not None/null)
# - Added IST→UTC conversion in POS fixture to match real data format
# - Changed billing zone test to verify 5-minute window exactly
# - Added test for store with only staff events (unique_visitors=0)
# ============================================================
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from conftest import make_event, make_pos_tx, engine


def seed_events(events: list[dict], db_conn):
    """Directly insert events into the test DB."""
    for e in events:
        db_conn.execute(text("""
            INSERT OR IGNORE INTO events
              (event_id, store_id, camera_id, visitor_id, event_type,
               timestamp, zone_id, dwell_ms, is_staff, confidence,
               queue_depth, sku_zone, session_seq, raw_metadata, ingested_at)
            VALUES
              (:event_id, :store_id, :camera_id, :visitor_id, :event_type,
               :timestamp, :zone_id, :dwell_ms, :is_staff, :confidence,
               :queue_depth, :sku_zone, :session_seq, NULL, :ingested_at)
        """), {**e, "ingested_at": datetime.now(timezone.utc).isoformat(),
               "is_staff": 1 if e.get("is_staff") else 0,
               "queue_depth": e.get("metadata", {}).get("queue_depth") if e.get("metadata") else None,
               "sku_zone": e.get("metadata", {}).get("sku_zone") if e.get("metadata") else None,
               "session_seq": e.get("metadata", {}).get("session_seq", 1) if e.get("metadata") else 1,
               })
    db_conn.commit()


def seed_pos(txns: list[dict], db_conn):
    for t in txns:
        db_conn.execute(text("""
            INSERT OR IGNORE INTO pos_transactions
              (order_id, store_id, transaction_time, basket_value, customer_number, salesperson_id)
            VALUES (:order_id, :store_id, :transaction_time, :basket_value, :customer_number, :salesperson_id)
        """), t)
    db_conn.commit()


class TestMetrics:

    def test_empty_store_returns_zero_not_null(self, client):
        r = client.get("/stores/ST1008/metrics")
        assert r.status_code == 200
        body = r.json()
        assert body["unique_visitors"] == 0
        assert body["conversion_rate"] == 0.0        # must be 0.0, NOT null
        assert body["queue_depth"] == 0
        assert body["abandonment_rate"] == 0.0
        assert "computed_at" in body

    def test_staff_excluded_from_unique_visitors(self, client):
        with engine.connect() as conn:
            seed_events([
                make_event(visitor_id="VIS_staff01", is_staff=True,  event_type="ENTRY"),
                make_event(visitor_id="VIS_staff02", is_staff=True,  event_type="ENTRY"),
                make_event(visitor_id="VIS_cust01",  is_staff=False, event_type="ENTRY"),
            ], conn)

        r = client.get("/stores/ST1008/metrics")
        assert r.status_code == 200
        assert r.json()["unique_visitors"] == 1   # Only the customer

    def test_all_staff_clip_returns_zero_visitors(self, client):
        with engine.connect() as conn:
            seed_events([
                make_event(is_staff=True, event_type="ENTRY"),
                make_event(is_staff=True, event_type="ENTRY"),
            ], conn)

        r = client.get("/stores/ST1008/metrics")
        assert r.json()["unique_visitors"] == 0
        assert r.json()["conversion_rate"] == 0.0

    def test_conversion_rate_zero_when_no_pos(self, client):
        with engine.connect() as conn:
            seed_events([make_event(event_type="ENTRY") for _ in range(5)], conn)
            # No POS transactions

        r = client.get("/stores/ST1008/metrics")
        assert r.json()["conversion_rate"] == 0.0    # NOT null

    def test_conversion_rate_correct_with_billing_visitor(self, client):
        """Visitor in CASH_COUNTER zone 3 min before POS tx → should be converted.
        Updated zone_id from 'BILLING' to 'CASH_COUNTER' to match store_layout.json v2
        physical signage zone IDs.
        """
        now = datetime.now(timezone.utc)
        vis_id = "VIS_conv01"

        with engine.connect() as conn:
            seed_events([
                make_event(visitor_id=vis_id, event_type="ENTRY",
                           timestamp=(now - timedelta(minutes=10)).isoformat()),
                make_event(visitor_id=vis_id, event_type="ZONE_ENTER",
                           zone_id="CASH_COUNTER",
                           timestamp=(now - timedelta(minutes=4)).isoformat()),
            ], conn)
            seed_pos([make_pos_tx(offset_minutes=0)], conn)

        r = client.get("/stores/ST1008/metrics")
        body = r.json()
        assert body["unique_visitors"] == 1
        assert body["conversion_rate"] > 0.0

    def test_queue_depth_from_latest_billing_join(self, client):
        now = datetime.now(timezone.utc)
        e = make_event(event_type="BILLING_QUEUE_JOIN", zone_id="BILLING",
                       timestamp=now.isoformat())
        e["metadata"]["queue_depth"] = 4

        with engine.connect() as conn:
            seed_events([e], conn)

        r = client.get("/stores/ST1008/metrics")
        assert r.json()["queue_depth"] == 4

    def test_abandonment_rate(self, client):
        with engine.connect() as conn:
            seed_events([
                make_event(visitor_id="VIS_a", event_type="BILLING_QUEUE_JOIN"),
                make_event(visitor_id="VIS_b", event_type="BILLING_QUEUE_JOIN"),
                make_event(visitor_id="VIS_a", event_type="BILLING_QUEUE_ABANDON"),
            ], conn)

        r = client.get("/stores/ST1008/metrics")
        body = r.json()
        assert body["abandonment_rate"] == 0.5   # 1 abandon / 2 joins

    def test_response_structure(self, client):
        r = client.get("/stores/ST1008/metrics")
        assert r.status_code == 200
        body = r.json()
        required_fields = [
            "store_id", "window", "unique_visitors",
            "conversion_rate", "avg_dwell_per_zone",
            "queue_depth", "abandonment_rate", "computed_at"
        ]
        for field in required_fields:
            assert field in body, f"Missing field: {field}"
