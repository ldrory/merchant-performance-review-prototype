-- DuckDB schema for the Riskified performance-review pipeline.
-- Flow: CSV -> normalized DataFrames -> validation -> curated DuckDB tables.
-- Only curated tables are persisted (ELT-style raw_* tables are not used).
--
-- Every table carries lightweight lineage: source_file, source_sha256, loaded_at.
-- The kpi_facts_* business columns must stay in sync with FACT_COLUMNS in
-- src/metrics/engine.py (lineage columns are appended); a test guards against drift.

-- Drop legacy raw tables if a previous (ETL-style) run created them.
DROP TABLE IF EXISTS raw_kpis;
DROP TABLE IF EXISTS raw_profiles;
DROP TABLE IF EXISTS raw_evidence;

CREATE OR REPLACE TABLE merchants (
    merchant_id        VARCHAR PRIMARY KEY,  -- deterministic slug, the isolation key
    merchant_name      VARCHAR,
    pre_or_post        VARCHAR,
    business_structure VARCHAR,
    source_file        VARCHAR,
    source_sha256      VARCHAR,
    loaded_at          TIMESTAMP
);

CREATE OR REPLACE TABLE kpi_measures (
    merchant_id   VARCHAR,    -- canonical join/group key (slug)
    account_name  VARCHAR,    -- original name from the KPI CSV (reference)
    period        VARCHAR,    -- YYYY-MM
    kpi_name      VARCHAR,
    value         DOUBLE,
    source_file   VARCHAR,
    source_sha256 VARCHAR,
    loaded_at     TIMESTAMP
);

CREATE OR REPLACE TABLE evidence (
    merchant_id   VARCHAR,
    period        VARCHAR,
    event         VARCHAR,
    source_file   VARCHAR,
    source_sha256 VARCHAR,
    loaded_at     TIMESTAMP
);

CREATE OR REPLACE TABLE kpi_facts_monthly (
    merchant_id       VARCHAR,
    period            VARCHAR,   -- YYYY-MM
    quarter           VARCHAR,   -- e.g. 2025-Q3
    metric_id         VARCHAR,
    metric_name       VARCHAR,
    variant           VARCHAR,   -- cnt | sum
    value             DOUBLE,    -- displayed source of truth
    value_source      VARCHAR,   -- additive | provided | computed
    provided_value    DOUBLE,
    computed_value    DOUBLE,
    numerator         DOUBLE,
    denominator       DOUBLE,
    abs_diff          DOUBLE,
    rel_diff_pct      DOUBLE,
    validation_status VARCHAR,
    source_file       VARCHAR,
    source_sha256     VARCHAR,
    loaded_at         TIMESTAMP
);

CREATE OR REPLACE TABLE kpi_facts_quarterly (
    merchant_id       VARCHAR,
    period            VARCHAR,   -- carries the quarter label for quarterly facts
    quarter           VARCHAR,
    metric_id         VARCHAR,
    metric_name       VARCHAR,
    variant           VARCHAR,
    value             DOUBLE,
    value_source      VARCHAR,
    provided_value    DOUBLE,
    computed_value    DOUBLE,
    numerator         DOUBLE,
    denominator       DOUBLE,
    abs_diff          DOUBLE,
    rel_diff_pct      DOUBLE,
    validation_status VARCHAR,
    source_file       VARCHAR,
    source_sha256     VARCHAR,
    loaded_at         TIMESTAMP
);
