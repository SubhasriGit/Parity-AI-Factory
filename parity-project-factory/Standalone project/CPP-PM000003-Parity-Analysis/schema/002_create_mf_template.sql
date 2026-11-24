-- Template only. Replace {{STORE}} with a validated four-digit store identifier.
CREATE TABLE IF NOT EXISTS mf_data_{{STORE}} (
    STORE_ID       TEXT,
    PRODUCT_NUMBER TEXT,
    PRICE_NAME     TEXT,
    PRICE_TYPE     TEXT,
    DEAL_NUMBER    TEXT,
    PRICE          TEXT,
    EFFECTIVE_DATE TEXT,
    Comment        TEXT,
    snapshot_day   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mf_data_{{STORE}}_lookup
    ON mf_data_{{STORE}}(snapshot_day, PRODUCT_NUMBER, PRICE_NAME, DEAL_NUMBER, PRICE_TYPE);
