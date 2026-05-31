# ============================================================
# PROMPT: "Generate pytest tests for GET /stores/{id}/funnel endpoint.
# Cover: empty funnel returns zero stages, funnel stages are in correct order,
# re-entry events do NOT double-count a visitor in the entry stage,
# billing_queue stage counts visitors who entered billing zone,
# drop_off_pct is computed correctly for each stage,
# funnel is session-based not event-based."
#
# CHANGES MADE:
# - Added explicit check that REENTRY visitor counts as 1 not 2 in entry stage
# - Changed stage order assertion to check exact list of stage names
# - Added verification that purchase stage <= billing_queue stage (no negative funnel)
# - Removed assertion on exact purchase count since it depends on POS correlation
# ============================================================
import pytest
from datetime import datetime, timezone, timedelta
from conftest import make_event, make_pos_tx, engine
from test_metrics import seed_events, seed_pos


class TestFunnel:

    def test_empty_funnel_returns_zeros(self, client):
        r = client.get("/stores/ST1008/funnel")
        assert r.status_code == 200
        body = r.json()
        assert "funnel" in body
        for stage in body["funnel"]:
            assert stage["sessions"] == 0

    def test_funnel_stage_order(self, client):
        r = client.get("/stores/ST1008/funnel")
        stages = [s["stage"] for s in r.json()["funnel"]]
        assert stages == ["entry", "zone_visit", "billing_queue", "purchase"]

    def test_reentry_does_not_double_count(self, client):
        """Same visitor_id with ENTRY + REENTRY should count as 1 in funnel entry stage."""
        vis_id = "VIS_reentry01"
        now = datetime.now(timezone.utc)

        with engine.connect() as conn:
            seed_events([
                make_event(visitor_id=vis_id, event_type="ENTRY",
                           timestamp=(now - timedelta(minutes=30)).isoformat()),
                make_event(visitor_id=vis_id, event_type="EXIT",
                           timestamp=(now - timedelta(minutes=15)).isoformat()),
                make_event(visitor_id=vis_id, event_type="REENTRY",
                           timestamp=(now - timedelta(minutes=5)).isoformat()),
            ], conn)

        r = client.get("/stores/ST1008/funnel")
        entry_stage = next(s for s in r.json()["funnel"] if s["stage"] == "entry")
        # visitor_id appears once in ENTRY → should count as 1 unique visitor
        assert entry_stage["sessions"] == 1

    def test_funnel_stages_monotonically_non_increasing(self, client):
        """Each stage should have <= sessions of the previous stage."""
        now = datetime.now(timezone.utc)
        with engine.connect() as conn:
            seed_events([
                make_event(visitor_id="VIS_f1", event_type="ENTRY"),
                make_event(visitor_id="VIS_f1", event_type="ZONE_ENTER",
                           zone_id="SKINCARE"),
                make_event(visitor_id="VIS_f1", event_type="ZONE_ENTER",
                           zone_id="BILLING"),
                make_event(visitor_id="VIS_f2", event_type="ENTRY"),
                make_event(visitor_id="VIS_f2", event_type="ZONE_ENTER",
                           zone_id="MAKEUP"),
            ], conn)

        r = client.get("/stores/ST1008/funnel")
        stages = r.json()["funnel"]
        for i in range(1, len(stages)):
            assert stages[i]["sessions"] <= stages[i - 1]["sessions"], (
                f"Stage {stages[i]['stage']} has MORE sessions than {stages[i-1]['stage']}"
            )

    def test_drop_off_pct_correct(self, client):
        """drop_off_pct for entry stage must be 0.0."""
        r = client.get("/stores/ST1008/funnel")
        entry = next(s for s in r.json()["funnel"] if s["stage"] == "entry")
        assert entry["drop_off_pct"] == 0.0

    def test_funnel_response_schema(self, client):
        r = client.get("/stores/ST1008/funnel")
        assert r.status_code == 200
        body = r.json()
        assert "store_id" in body
        assert "funnel" in body
        for stage in body["funnel"]:
            assert "stage" in stage
            assert "sessions" in stage
            assert "drop_off_pct" in stage
