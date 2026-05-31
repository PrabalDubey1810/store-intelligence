"""
Test fixtures and shared utilities for Store Intelligence API tests.
Uses SQLite in-memory DB for fast, isolated test runs.
"""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Use SQLite for tests (no Docker needed)
TEST_DB_URL = "sqlite:///./test_store_intel.db"

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from database import Base, get_db
from main import app

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create test tables once per test session."""
    # Create all tables using raw SQL (compatible with SQLite)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                visitor_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                zone_id TEXT,
                dwell_ms INTEGER DEFAULT 0,
                is_staff INTEGER DEFAULT 0,
                confidence REAL NOT NULL,
                queue_depth INTEGER,
                sku_zone TEXT,
                session_seq INTEGER,
                raw_metadata TEXT,
                ingested_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_transactions (
                order_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                transaction_time TEXT NOT NULL,
                basket_value REAL DEFAULT 0,
                customer_number TEXT,
                salesperson_id TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stores (
                store_id TEXT PRIMARY KEY,
                store_name TEXT,
                city TEXT
            )
        """))
        conn.execute(text(
            "INSERT OR IGNORE INTO stores VALUES ('ST1008', 'Brigade_Bangalore', 'Bangalore')"
        ))
        conn.commit()
    yield
    # Cleanup — ignore Windows file lock errors
    import os
    try:
        if os.path.exists("test_store_intel.db"):
            os.remove("test_store_intel.db")
    except (PermissionError, OSError):
        pass  # Windows file lock — harmless, OS will clean up


@pytest.fixture(autouse=True)
def clean_events():
    """Clear events and POS transactions before each test."""
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM events"))
        conn.execute(text("DELETE FROM pos_transactions"))
        conn.commit()
    yield


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_event(
    store_id="ST1008",
    visitor_id=None,
    event_type="ENTRY",
    is_staff=False,
    zone_id=None,
    dwell_ms=0,
    confidence=0.9,
    session_seq=1,
    timestamp=None,
    camera_id="CAM_ENTRY_01",
    queue_depth=None,
) -> dict:
    """Factory for well-formed test events."""
    if visitor_id is None:
        visitor_id = f"VIS_{uuid.uuid4().hex[:6]}"
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "event_id":   str(uuid.uuid4()),
        "store_id":   store_id,
        "camera_id":  camera_id,
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp":  timestamp,
        "zone_id":    zone_id,
        "dwell_ms":   dwell_ms,
        "is_staff":   is_staff,
        "confidence": confidence,
        "metadata": {
            "queue_depth":  queue_depth,
            "sku_zone":     zone_id,
            "session_seq":  session_seq,
        }
    }


def make_pos_tx(store_id="ST1008", offset_minutes=-3, order_id=None):
    """Factory for POS transactions."""
    if order_id is None:
        order_id = f"ORD_{uuid.uuid4().hex[:8]}"
    txn_time = (datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)).isoformat()
    return {
        "order_id":        order_id,
        "store_id":        store_id,
        "transaction_time": txn_time,
        "basket_value":    1240.0,
        "customer_number": "9876543210",
        "salesperson_id":  "CL2727",
    }
