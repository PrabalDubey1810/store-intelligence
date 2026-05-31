-- Store Intelligence DB Schema
-- Run automatically by Docker on first startup

CREATE TABLE IF NOT EXISTS stores (
    store_id    TEXT PRIMARY KEY,
    store_name  TEXT,
    city        TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    event_id      TEXT PRIMARY KEY,
    store_id      TEXT NOT NULL,
    camera_id     TEXT NOT NULL,
    visitor_id    TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL,
    zone_id       TEXT,
    dwell_ms      INTEGER DEFAULT 0,
    is_staff      BOOLEAN NOT NULL DEFAULT FALSE,
    confidence    REAL NOT NULL,
    queue_depth   INTEGER,
    sku_zone      TEXT,
    session_seq   INTEGER,
    raw_metadata  JSONB,
    ingested_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_store_ts   ON events (store_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_visitor     ON events (visitor_id);
CREATE INDEX IF NOT EXISTS idx_events_type        ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_zone        ON events (zone_id);
CREATE INDEX IF NOT EXISTS idx_events_staff       ON events (is_staff);

CREATE TABLE IF NOT EXISTS pos_transactions (
    order_id          TEXT PRIMARY KEY,
    store_id          TEXT NOT NULL,
    transaction_time  TIMESTAMPTZ NOT NULL,
    basket_value      REAL DEFAULT 0,
    customer_number   TEXT,
    salesperson_id    TEXT,
    loaded_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pos_store_ts ON pos_transactions (store_id, transaction_time);

-- Seed known store
INSERT INTO stores (store_id, store_name, city)
VALUES ('ST1008', 'Brigade_Bangalore', 'Bangalore')
ON CONFLICT DO NOTHING;
