CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS traffic_records (
  id UUID DEFAULT gen_random_uuid(),
  queried_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  origin_lat DOUBLE PRECISION NOT NULL,
  origin_lng DOUBLE PRECISION NOT NULL,
  dest_lat DOUBLE PRECISION NOT NULL,
  dest_lng DOUBLE PRECISION NOT NULL,
  label TEXT,
  duration_seconds INTEGER,
  static_duration_seconds INTEGER,
  delay_seconds INTEGER,
  congestion_level TEXT,
  overall_condition TEXT,
  cache_hit BOOLEAN DEFAULT FALSE,
  raw_response JSONB
);

SELECT create_hypertable('traffic_records', 'queried_at', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS traffic_records_route_time_idx
  ON traffic_records (origin_lat, origin_lng, dest_lat, dest_lng, queried_at DESC);

