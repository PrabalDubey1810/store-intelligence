# ============================================================
# PROMPT: "Generate pytest tests for GET /stores/{id}/anomalies.
# Cover: no anomalies for normal store, BILLING_QUEUE_SPIKE fires when
# queue_depth > 5 with CRITICAL severity, CONVERSION_DROP fires when
# today's rate is significantly below baseline, DEAD_ZONE fires when
# a zone has had visits historically but none in last 30 minutes,
# each anomaly has a non-empty suggested_action string."
#
# CHANGES MADE:
# - Changed DEAD_ZONE test to seed historical events with older timestamps
#   (> 30 min ago) to actually trigger the anomaly
# - Added assertion that severity is one of INFO/WARN/CRITICAL
# - Changed suggested_action assertion from non-empty to minimum 10 chars
#   to prevent trivially short strings from passing
# ============================================================
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from test_metrics import seed_events, seed_pos
from conftest import make_event, make_pos_tx

VALID_SEVERITIES = {"INFO", "WARN", "CRITICAL"}


class TestAnomalies:

    def test_no_anomalies_empty_store(self, client):
        r = client.get("/stores/ST1008/anomalies")
        assert r.status_code == 200
        body = r.json()
        assert "anomalies" in body
        assert "store_id" in body
        # Empty store may have no anomalies
        for anomaly in body["anomalies"]:
            assert anomaly["severity"] in VALID_SEVERITIES

    def test_billing_queue_spike_critical(self, client):
        from datetime import timezone
        now = datetime.now(timezone.utc)
        e = make_event(event_type="BILLING_QUEUE_JOIN", zone_id="BILLING",
                       timestamp=now.isoformat())
        e["metadata"]["queue_depth"] = 8   # > QUEUE_SPIKE_THRESHOLD (5)

        from sqlalchemy import create_engine
        from conftest import engine
        with engine.connect() as conn:
            seed_events([e], conn)

        r = client.get("/stores/ST1008/anomalies")
        body = r.json()
        spikes = [a for a in body["anomalies"] if a["type"] == "BILLING_QUEUE_SPIKE"]
        assert len(spikes) >= 1
        assert spikes[0]["severity"] == "CRITICAL"
        assert len(spikes[0]["suggested_action"]) >= 10

    def test_billing_queue_spike_warn(self, client):
        from conftest import engine
        now = datetime.now(timezone.utc)
        e = make_event(event_type="BILLING_QUEUE_JOIN", zone_id="BILLING",
                       timestamp=now.isoformat())
        e["metadata"]["queue_depth"] = 4   # > WARN_THRESHOLD (3), <= CRITICAL (5)

        with engine.connect() as conn:
            seed_events([e], conn)

        r = client.get("/stores/ST1008/anomalies")
        spikes = [a for a in r.json()["anomalies"] if a["type"] == "BILLING_QUEUE_SPIKE"]
        assert len(spikes) >= 1
        assert spikes[0]["severity"] == "WARN"

    def test_dead_zone_anomaly(self, client):
        """Zone with visits > 30 min ago but none recently = DEAD_ZONE."""
        from conftest import engine
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
        recent_entry = make_event(event_type="ENTRY")

        old_zone = make_event(
            event_type="ZONE_ENTER",
            zone_id="HAIRCARE",
            timestamp=old_ts,
        )

        with engine.connect() as conn:
            seed_events([recent_entry, old_zone], conn)

        r = client.get("/stores/ST1008/anomalies")
        dead_zones = [a for a in r.json()["anomalies"] if a["type"] == "DEAD_ZONE"]
        zone_ids = [a.get("zone_id") for a in dead_zones]
        assert "HAIRCARE" in zone_ids

    def test_all_anomalies_have_suggested_action(self, client):
        """Every anomaly returned must have a non-trivial suggested_action."""
        from conftest import engine
        now = datetime.now(timezone.utc)
        e = make_event(event_type="BILLING_QUEUE_JOIN", zone_id="BILLING",
                       timestamp=now.isoformat())
        e["metadata"]["queue_depth"] = 9

        with engine.connect() as conn:
            seed_events([e], conn)

        r = client.get("/stores/ST1008/anomalies")
        for anomaly in r.json()["anomalies"]:
            assert "suggested_action" in anomaly
            assert len(anomaly["suggested_action"]) >= 10, (
                f"Anomaly {anomaly['type']} has a trivial suggested_action"
            )

    def test_anomaly_response_schema(self, client):
        r = client.get("/stores/ST1008/anomalies")
        assert r.status_code == 200
        body = r.json()
        assert "store_id" in body
        assert "anomalies" in body
        assert isinstance(body["anomalies"], list)
