-- XY-P0-04: 订单回调幂等 external_event_id
-- SQLite migration

CREATE TABLE IF NOT EXISTS order_callback_dedup (
    external_event_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
