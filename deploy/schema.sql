-- Mycelium Sentinel — TimescaleDB schema for spike events.
--
-- Run with: docker exec -i deploy-timescale-1 psql -U mycelium -d mycelium < deploy/schema.sql

CREATE TABLE IF NOT EXISTS spike_events (
    time          TIMESTAMPTZ NOT NULL,
    channel       INTEGER NOT NULL,
    count         INTEGER NOT NULL,
    amplitude     REAL NOT NULL,
    amplitude_mean REAL NOT NULL,
    amplitude_std  REAL NOT NULL,
    amplitude_min  REAL NOT NULL,
    amplitude_max  REAL NOT NULL,
    isi_mean      REAL NOT NULL,
    isi_std       REAL NOT NULL,
    isi_min       REAL NOT NULL,
    isi_max       REAL NOT NULL,
    burst_index   REAL NOT NULL,
    rate          REAL NOT NULL,
    histogram     INTEGER[] NOT NULL,
    sim_clock_factor REAL NOT NULL
);

-- Convert to a TimescaleDB hypertable, partitioned by time.
SELECT create_hypertable('spike_events', 'time', if_not_exists => TRUE);

-- Useful indexes for the dashboard queries.
CREATE INDEX IF NOT EXISTS idx_spike_events_channel ON spike_events (channel, time DESC);