PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS _metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS cpp_price_packets (
    packetId              INTEGER PRIMARY KEY,
    storeNumber           TEXT NOT NULL,
    header                TEXT,
    body                  TEXT,
    recCreationDateTime   TEXT,
    lastModifiedDateTime  TEXT,
    errorMessage          TEXT,
    isProcessed           INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cpp_price_packets_store ON cpp_price_packets(storeNumber);
CREATE INDEX IF NOT EXISTS idx_cpp_price_packets_created ON cpp_price_packets(recCreationDateTime);

CREATE TABLE IF NOT EXISTS deal_price_master (
    promoProductPriceId               INTEGER PRIMARY KEY,
    productNumber                     TEXT,
    zoneNumber                        TEXT,
    zoneType                          TEXT,
    dealNumber                        TEXT,
    dealYear                          TEXT,
    dealType                          TEXT,
    promoRetailPrice                  TEXT,
    promoRetailPriceEffectiveDate     TEXT,
    promoDealerPrice                  TEXT,
    promoDealerPriceEffectiveDate     TEXT,
    lastModifiedDateTime              TEXT,
    recCreationDateTime               TEXT,
    promoRetailPriceEndDate           TEXT,
    promoDealerPriceEndDate           TEXT
);
CREATE INDEX IF NOT EXISTS idx_deal_price_master_product ON deal_price_master(productNumber);
CREATE INDEX IF NOT EXISTS idx_deal_price_master_deal ON deal_price_master(dealNumber, dealYear);
CREATE INDEX IF NOT EXISTS idx_deal_price_master_zone ON deal_price_master(zoneNumber, zoneType);

CREATE TABLE IF NOT EXISTS regular_price_master (
    regProductPriceId                  INTEGER PRIMARY KEY,
    productNumber                      TEXT,
    zoneNumber                         TEXT,
    zoneType                           TEXT,
    regularRetailPrice                 TEXT,
    regularRetailPriceEffectiveDate    TEXT,
    regularRetailPriceEndDate          TEXT,
    regularDealerPrice                 TEXT,
    regularDealerPriceEffectiveDate    TEXT,
    regularDealerPriceEndDate          TEXT,
    lastModifiedDateTime               TEXT,
    recCreationDateTime                TEXT,
    regularRetailChangeType            TEXT,
    regularDealerChangeType            TEXT
);
CREATE INDEX IF NOT EXISTS idx_regular_price_master_product ON regular_price_master(productNumber);
CREATE INDEX IF NOT EXISTS idx_regular_price_master_zone ON regular_price_master(zoneNumber, zoneType);

CREATE TABLE IF NOT EXISTS zone_store_relation (
    storeNumber          TEXT NOT NULL,
    zoneNumber           TEXT NOT NULL,
    recCreationDateTime  TEXT,
    PRIMARY KEY (storeNumber, zoneNumber)
);
CREATE INDEX IF NOT EXISTS idx_zone_store_relation_store ON zone_store_relation(storeNumber);
CREATE INDEX IF NOT EXISTS idx_zone_store_relation_zone ON zone_store_relation(zoneNumber);

CREATE TABLE IF NOT EXISTS staging_product_price (
    eventId                    TEXT NOT NULL,
    eventType                  TEXT,
    productNumber              TEXT,
    zoneNumber                 TEXT,
    zoneType                   TEXT,
    eventAction                TEXT,
    dealNumber                 TEXT,
    dealYear                   TEXT,
    dealType                   TEXT,
    retailPrice                TEXT,
    retailPriceEffectiveDate   TEXT,
    retailPriceEndDate         TEXT,
    dealerPrice                TEXT,
    dealerPriceEffectiveDate   TEXT,
    dealerPriceEndDate         TEXT,
    rawRecCreationDateTime     TEXT,
    recCreationDateTime        TEXT,
    retailChangeType           TEXT,
    dealerChangeType           TEXT,
    rowHash                    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_product_price_row_hash ON staging_product_price(rowHash);
CREATE INDEX IF NOT EXISTS idx_staging_product_price_event ON staging_product_price(eventId);
CREATE INDEX IF NOT EXISTS idx_staging_product_price_product ON staging_product_price(productNumber);
CREATE INDEX IF NOT EXISTS idx_staging_product_price_deal ON staging_product_price(dealNumber, dealYear);
CREATE INDEX IF NOT EXISTS idx_staging_product_price_created ON staging_product_price(recCreationDateTime);

CREATE TABLE IF NOT EXISTS mismatch_input (
    row_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    day               TEXT NOT NULL,
    direction         TEXT NOT NULL,
    store             TEXT NOT NULL,
    offering_number   TEXT NOT NULL,
    deal_number       TEXT NOT NULL,
    price_type        TEXT NOT NULL,
    effective_date    TEXT NOT NULL,
    dealer_cost_price TEXT NOT NULL,
    retail_price      TEXT NOT NULL,
    casting_price     TEXT NOT NULL,
    timestamp_utc     TEXT NOT NULL,
    message_id        TEXT
);
CREATE INDEX IF NOT EXISTS ix_mi_key ON mismatch_input(store, offering_number, deal_number, price_type, effective_date);
CREATE INDEX IF NOT EXISTS ix_mi_dir ON mismatch_input(direction);
CREATE INDEX IF NOT EXISTS ix_mi_day ON mismatch_input(day);

CREATE TABLE IF NOT EXISTS mismatch_verdict (
    row_id              INTEGER PRIMARY KEY REFERENCES mismatch_input(row_id),
    classification      TEXT NOT NULL,
    kd_code             TEXT,
    confidence          REAL NOT NULL,
    hypothesis          TEXT NOT NULL,
    supporting_evidence TEXT NOT NULL,
    missing_evidence    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cpp_data (
    STORE_NUMBER   TEXT NOT NULL,
    PRODUCT_NUMBER TEXT NOT NULL,
    PRICE_NAME     TEXT NOT NULL,
    PRICE_TYPE     TEXT NOT NULL,
    DEAL_NUMBER    TEXT NOT NULL,
    PRICE          TEXT NOT NULL,
    EFFECTIVE_DATE TEXT,
    SNAPSHOT_DAY   TEXT,
    Comment        TEXT
);
CREATE INDEX IF NOT EXISTS ix_cpp_data_key ON cpp_data(STORE_NUMBER, PRODUCT_NUMBER, PRICE_NAME, DEAL_NUMBER, PRICE_TYPE);
CREATE INDEX IF NOT EXISTS ix_cpp_data_day_key ON cpp_data(SNAPSHOT_DAY, STORE_NUMBER, PRODUCT_NUMBER, PRICE_NAME, DEAL_NUMBER, PRICE_TYPE);
CREATE INDEX IF NOT EXISTS ix_cpp_data_prod ON cpp_data(PRODUCT_NUMBER, PRICE_NAME);

PRAGMA user_version = 1;
