-- ============================================================================
-- Autonomous Incident Engineer — Database Initialization
-- ============================================================================

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ─── Metrics (time-series) ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS metrics (
    time        TIMESTAMPTZ NOT NULL,
    service     TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    labels      JSONB DEFAULT '{}'
);

SELECT create_hypertable('metrics', 'time', if_not_exists => TRUE);

-- ─── Traces (distributed tracing spans) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS traces (
    time            TIMESTAMPTZ NOT NULL,
    trace_id        TEXT NOT NULL,
    span_id         TEXT NOT NULL,
    parent_span_id  TEXT DEFAULT '',
    service         TEXT NOT NULL,
    operation_name  TEXT NOT NULL,
    duration_ms     DOUBLE PRECISION NOT NULL,
    status          TEXT NOT NULL,
    error_message   TEXT DEFAULT '',
    attributes      JSONB DEFAULT '{}'
);

SELECT create_hypertable('traces', 'time', if_not_exists => TRUE);

-- ─── Incidents (metadata + analysis results) ────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
    id                TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'open',
    severity          TEXT NOT NULL DEFAULT 'warning',
    detected_at       TIMESTAMPTZ NOT NULL,
    resolved_at       TIMESTAMPTZ,
    affected_services JSONB DEFAULT '[]',
    anomaly_data      JSONB DEFAULT '{}',
    analysis_result   JSONB DEFAULT '{}',
    postmortem        TEXT DEFAULT '',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Indexes ────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_metrics_service ON metrics (service, time DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics (metric_name, time DESC);
CREATE INDEX IF NOT EXISTS idx_traces_service ON traces (service, time DESC);
CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON traces (trace_id);
CREATE INDEX IF NOT EXISTS idx_traces_status ON traces (status, time DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents (status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents (severity);
CREATE INDEX IF NOT EXISTS idx_incidents_detected ON incidents (detected_at DESC);
