"""DuckDB warehouse: connection and schema for bronze, silver, gold and run metadata."""
from __future__ import annotations

from pathlib import Path

import duckdb

SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS run_seq START 1;

CREATE TABLE IF NOT EXISTS pipeline_run (
    run_id            INTEGER PRIMARY KEY,
    started_at        TIMESTAMP,
    finished_at       TIMESTAMP,
    status            VARCHAR,          -- running | success | failed
    files_new         INTEGER,
    files_skipped     INTEGER,
    files_failed      INTEGER,
    gold_rows_changed INTEGER,
    message           VARCHAR
);

-- Bronze: one row per distinct raw file (content hash). Files are never modified or deleted.
CREATE TABLE IF NOT EXISTS bronze_file (
    file_id         VARCHAR PRIMARY KEY,  -- sha256 of content
    source_id       VARCHAR NOT NULL,
    original_name   VARCHAR NOT NULL,
    bronze_path     VARCHAR NOT NULL,     -- relative to the warehouse directory
    size_bytes      BIGINT,
    url             VARCHAR,
    published_at    TIMESTAMPTZ,          -- from the source listing, when known
    note            VARCHAR,
    first_seen_run  INTEGER,
    ingested_at     TIMESTAMP,
    parse_status    VARCHAR,              -- pending | parsed | failed
    parse_error     VARCHAR,
    parser_version  VARCHAR,
    parse_signature VARCHAR,              -- hash(parser version + source's state aliases)
    operating_date  DATE,
    reporting_date  DATE
);

-- Upgrade warehouses created before parse_signature existed.
ALTER TABLE bronze_file ADD COLUMN IF NOT EXISTS parse_signature VARCHAR;

-- Silver: standardised state-day values, one row per (file, state). All versions kept.
CREATE TABLE IF NOT EXISTS silver_state_daily (
    file_id                        VARCHAR NOT NULL,
    source_id                      VARCHAR NOT NULL,
    state_code                     VARCHAR NOT NULL,
    operating_date                 DATE NOT NULL,
    energy_met_mu                  DOUBLE,
    energy_shortage_mu             DOUBLE,
    energy_requirement_reported_mu DOUBLE,
    raw_label                      VARCHAR,
    location                       VARCHAR,
    parser_version                 VARCHAR,
    PRIMARY KEY (file_id, state_code)
);

-- Current version per (source, state, day): latest publication wins; arrival order breaks ties
-- and is used when the publication time is unknown.
CREATE OR REPLACE VIEW silver_state_daily_current AS
SELECT * EXCLUDE (rn) FROM (
    SELECT s.*, b.published_at, b.ingested_at, b.original_name,
           COUNT(*)     OVER w_all AS n_versions,
           ROW_NUMBER() OVER (PARTITION BY s.source_id, s.state_code, s.operating_date
                              ORDER BY COALESCE(b.published_at, b.ingested_at::TIMESTAMPTZ) DESC,
                                       b.ingested_at DESC, s.file_id) AS rn
    FROM silver_state_daily s JOIN bronze_file b USING (file_id)
    WINDOW w_all AS (PARTITION BY s.source_id, s.state_code, s.operating_date)
) WHERE rn = 1;

CREATE TABLE IF NOT EXISTS dq_result (
    run_id         INTEGER,
    check_id       VARCHAR,   -- e.g. parse_failed, cross_source_disagree
    severity       VARCHAR,   -- ERROR | WARN | INFO
    scope          VARCHAR,   -- file | row | cross_source | coverage
    source_id      VARCHAR,
    file_id        VARCHAR,
    state_code     VARCHAR,
    operating_date DATE,
    detail         VARCHAR
);

-- Gold: one trusted row per (state, day) in scope, including explicit gaps.
CREATE TABLE IF NOT EXISTS gold_state_daily_energy (
    state_code                VARCHAR NOT NULL,
    state_name                VARCHAR,
    region                    VARCHAR,
    operating_date            DATE NOT NULL,
    energy_required_mu        DOUBLE,
    energy_supplied_mu        DOUBLE,
    energy_shortfall_mu       DOUBLE,
    shortfall_pct             DOUBLE,
    primary_source            VARCHAR,
    primary_file              VARCHAR,
    corroborating_source      VARCHAR,
    corroborating_supplied_mu DOUBLE,
    supplied_diff_mu          DOUBLE,
    n_sources                 INTEGER,
    is_revised                BOOLEAN,
    quality_status            VARCHAR,  -- OK | WARN | MISSING
    quality_notes             VARCHAR,
    last_changed_run          INTEGER,
    PRIMARY KEY (state_code, operating_date)
);

-- Audit trail of every change to a gold row.
CREATE TABLE IF NOT EXISTS gold_state_daily_history (
    run_id           INTEGER,
    change_type      VARCHAR,   -- insert | update
    state_code       VARCHAR,
    operating_date   DATE,
    old_supplied_mu  DOUBLE,
    new_supplied_mu  DOUBLE,
    old_shortfall_mu DOUBLE,
    new_shortfall_mu DOUBLE,
    old_status       VARCHAR,
    new_status       VARCHAR,
    old_primary_file VARCHAR,
    new_primary_file VARCHAR,
    old_notes        VARCHAR,
    new_notes        VARCHAR
);

CREATE OR REPLACE VIEW dq_latest AS
SELECT * FROM dq_result
WHERE run_id = (SELECT MAX(run_id) FROM pipeline_run WHERE status = 'success');
"""


def connect(warehouse_dir: Path) -> duckdb.DuckDBPyConnection:
    warehouse_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(warehouse_dir / "pgi.duckdb"))
    con.execute("SET TimeZone = 'Asia/Kolkata'")
    con.execute(SCHEMA)
    return con
