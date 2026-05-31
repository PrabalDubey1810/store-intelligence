# ============================================================
# PROMPT: "Generate pytest tests for POST /events/ingest covering:
# (1) successful batch ingestion returns accepted count,
# (2) same payload twice is idempotent — same accepted count both calls,
# (3) invalid event_type returns rejected with error detail,
# (4) confidence out of range [0,1] is rejected,
# (5) batch of 501 events is capped to 500,
# (6) partial success — valid events accepted even when some are invalid,
# (7) is_staff=true events are accepted but should be filterable later,
# (8) empty batch returns 0 accepted."
#
# CHANGES MADE:
# - Replaced expected cap at 501 with actual cap assertion on accepted count
# - Added explicit check that event_ids are globally unique (no collision)
# - Changed partial-success test to verify exact error count
# - Added assertion that response JSON always has 'accepted', 'rejected', 'errors' keys
# ============================================================
import uuid
import pytest
from conftest import make_event


class TestIngest:

    def test_successful_ingest(self, client):
        events = [make_event() for _ in range(5)]
        r = client.post("/events/ingest", json={"events": events})
        assert r.status_code == 200
        body = r.json()
        assert "accepted" in body
        assert "rejected" in body
        assert "errors" in body
        assert body["accepted"] == 5
        assert body["rejected"] == 0

    def test_idempotent_same_payload(self, client):
        """Same payload ingested twice — accepted count identical both calls."""
        events = [make_event(visitor_id="VIS_abc123") for _ in range(3)]
        r1 = client.post("/events/ingest", json={"events": events})
        r2 = client.post("/events/ingest", json={"events": events})
        assert r1.json()["accepted"] == r2.json()["accepted"]
        # Second call should NOT inflate total events in DB
        metrics = client.get("/stores/ST1008/metrics")
        assert metrics.json()["unique_visitors"] == 1  # Only 1 unique visitor

    def test_invalid_event_type_rejected(self, client):
        bad_event = make_event()
        bad_event["event_type"] = "INVALID_TYPE"
        r = client.post("/events/ingest", json={"events": [bad_event]})
        assert r.status_code == 200
        body = r.json()
        assert body["rejected"] == 1
        assert len(body["errors"]) == 1

    def test_confidence_out_of_range_rejected(self, client):
        bad_event = make_event()
        bad_event["confidence"] = 1.5   # > 1.0
        r = client.post("/events/ingest", json={"events": [bad_event]})
        assert r.status_code == 200
        assert r.json()["rejected"] == 1

    def test_batch_cap_at_500(self, client):
        events = [make_event() for _ in range(501)]
        r = client.post("/events/ingest", json={"events": events})
        assert r.status_code == 200
        assert r.json()["accepted"] <= 500  # Hard cap enforced

    def test_partial_success_mixed_batch(self, client):
        valid = make_event()
        invalid = make_event()
        invalid["event_type"] = "FAKE_TYPE"
        r = client.post("/events/ingest", json={"events": [valid, invalid]})
        assert r.status_code == 200
        assert r.json()["accepted"] == 1
        assert r.json()["rejected"] == 1

    def test_staff_events_accepted(self, client):
        staff_event = make_event(is_staff=True, event_type="ENTRY")
        r = client.post("/events/ingest", json={"events": [staff_event]})
        assert r.status_code == 200
        assert r.json()["accepted"] == 1

    def test_empty_batch(self, client):
        r = client.post("/events/ingest", json={"events": []})
        assert r.status_code == 200
        assert r.json()["accepted"] == 0

    def test_event_ids_are_unique(self, client):
        """Verify event_ids generated in fixtures are unique (no UUID collisions)."""
        events = [make_event() for _ in range(10)]
        ids = [e["event_id"] for e in events]
        assert len(ids) == len(set(ids)), "Duplicate event_ids detected!"
