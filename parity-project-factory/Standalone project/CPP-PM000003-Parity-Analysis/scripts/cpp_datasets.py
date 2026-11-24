"""Immutable CPP dataset contracts used by loaders, validators, and tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    table: str
    csv_filename: str
    columns: Tuple[str, ...]
    create_sql: str
    index_sqls: Tuple[str, ...]
    insert_or_ignore: bool = True
    pk_col: Optional[str] = None
    truncate_before_load: bool = False

    @property
    def insert_sql(self) -> str:
        verb = "INSERT OR IGNORE" if self.insert_or_ignore else "INSERT"
        placeholders = ", ".join("?" for _ in self.columns)
        return f"{verb} INTO {self.table} ({', '.join(self.columns)}) VALUES ({placeholders})"


CPP_SPEC = DatasetSpec(
    key="cpp",
    table="cpp_price_packets",
    csv_filename="corpPricePackets.csv",
    columns=("packetId", "storeNumber", "header", "body", "recCreationDateTime",
             "lastModifiedDateTime", "errorMessage", "isProcessed"),
    create_sql="""CREATE TABLE IF NOT EXISTS cpp_price_packets (
        packetId INTEGER PRIMARY KEY, storeNumber TEXT NOT NULL, header TEXT, body TEXT,
        recCreationDateTime TEXT, lastModifiedDateTime TEXT, errorMessage TEXT, isProcessed INTEGER)""",
    index_sqls=(
        "CREATE INDEX IF NOT EXISTS idx_cpp_price_packets_store ON cpp_price_packets(storeNumber)",
        "CREATE INDEX IF NOT EXISTS idx_cpp_price_packets_created ON cpp_price_packets(recCreationDateTime)",
    ),
    pk_col="packetId",
)

DEAL_SPEC = DatasetSpec(
    key="deal",
    table="deal_price_master",
    csv_filename="dealPriceMaster.csv",
    columns=("promoProductPriceId", "productNumber", "zoneNumber", "zoneType", "dealNumber", "dealYear", "dealType", "promoRetailPrice", "promoRetailPriceEffectiveDate",
             "promoDealerPrice", "promoDealerPriceEffectiveDate", "lastModifiedDateTime", "recCreationDateTime", "promoRetailPriceEndDate", "promoDealerPriceEndDate"),
    create_sql="""CREATE TABLE IF NOT EXISTS deal_price_master (
        promoProductPriceId INTEGER PRIMARY KEY, productNumber TEXT, zoneNumber TEXT, zoneType TEXT,
        dealNumber TEXT, dealYear TEXT, dealType TEXT, promoRetailPrice TEXT,
        promoRetailPriceEffectiveDate TEXT, promoDealerPrice TEXT, promoDealerPriceEffectiveDate TEXT,
        lastModifiedDateTime TEXT, recCreationDateTime TEXT, promoRetailPriceEndDate TEXT,
        promoDealerPriceEndDate TEXT)""",
    index_sqls=(
        "CREATE INDEX IF NOT EXISTS idx_deal_price_master_product ON deal_price_master(productNumber)",
        "CREATE INDEX IF NOT EXISTS idx_deal_price_master_deal ON deal_price_master(dealNumber, dealYear)",
        "CREATE INDEX IF NOT EXISTS idx_deal_price_master_zone ON deal_price_master(zoneNumber, zoneType)",
    ),
    pk_col="promoProductPriceId",
    truncate_before_load=True,
)

REG_SPEC = DatasetSpec(
    key="regular",
    table="regular_price_master",
    csv_filename="regularPriceMaster.csv",
    columns=("regProductPriceId", "productNumber", "zoneNumber", "zoneType", "regularRetailPrice", "regularRetailPriceEffectiveDate", "regularRetailPriceEndDate", "regularDealerPrice",
             "regularDealerPriceEffectiveDate", "regularDealerPriceEndDate", "lastModifiedDateTime", "recCreationDateTime", "regularRetailChangeType", "regularDealerChangeType"),
    create_sql="""CREATE TABLE IF NOT EXISTS regular_price_master (
        regProductPriceId INTEGER PRIMARY KEY, productNumber TEXT, zoneNumber TEXT, zoneType TEXT,
        regularRetailPrice TEXT, regularRetailPriceEffectiveDate TEXT, regularRetailPriceEndDate TEXT,
        regularDealerPrice TEXT, regularDealerPriceEffectiveDate TEXT, regularDealerPriceEndDate TEXT,
        lastModifiedDateTime TEXT, recCreationDateTime TEXT, regularRetailChangeType TEXT,
        regularDealerChangeType TEXT)""",
    index_sqls=(
        "CREATE INDEX IF NOT EXISTS idx_regular_price_master_product ON regular_price_master(productNumber)",
        "CREATE INDEX IF NOT EXISTS idx_regular_price_master_zone ON regular_price_master(zoneNumber, zoneType)",
    ),
    pk_col="regProductPriceId",
    truncate_before_load=True,
)

ZONE_SPEC = DatasetSpec(
    key="zone",
    table="zone_store_relation",
    csv_filename="zoneStoreRelation.csv",
    columns=("storeNumber", "zoneNumber", "recCreationDateTime"),
    create_sql="""CREATE TABLE IF NOT EXISTS zone_store_relation (
        storeNumber TEXT NOT NULL, zoneNumber TEXT NOT NULL, recCreationDateTime TEXT,
        PRIMARY KEY (storeNumber, zoneNumber))""",
    index_sqls=(
        "CREATE INDEX IF NOT EXISTS idx_zone_store_relation_store ON zone_store_relation(storeNumber)",
        "CREATE INDEX IF NOT EXISTS idx_zone_store_relation_zone ON zone_store_relation(zoneNumber)",
    ),
    truncate_before_load=True,
)

STAGING_SPEC = DatasetSpec(
    key="staging",
    table="staging_product_price",
    csv_filename="stagingProductPrice.csv",
    columns=("eventId", "eventType", "productNumber", "zoneNumber", "zoneType", "eventAction", "dealNumber", "dealYear", "dealType", "retailPrice", "retailPriceEffectiveDate",
             "retailPriceEndDate", "dealerPrice", "dealerPriceEffectiveDate", "dealerPriceEndDate", "rawRecCreationDateTime", "recCreationDateTime", "retailChangeType", "dealerChangeType", "rowHash"),
    create_sql="""CREATE TABLE IF NOT EXISTS staging_product_price (
        eventId TEXT NOT NULL, eventType TEXT, productNumber TEXT, zoneNumber TEXT, zoneType TEXT,
        eventAction TEXT, dealNumber TEXT, dealYear TEXT, dealType TEXT, retailPrice TEXT,
        retailPriceEffectiveDate TEXT, retailPriceEndDate TEXT, dealerPrice TEXT,
        dealerPriceEffectiveDate TEXT, dealerPriceEndDate TEXT, rawRecCreationDateTime TEXT,
        recCreationDateTime TEXT, retailChangeType TEXT, dealerChangeType TEXT, rowHash TEXT NOT NULL)""",
    index_sqls=(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_staging_product_price_row_hash ON staging_product_price(rowHash)",
        "CREATE INDEX IF NOT EXISTS idx_staging_product_price_event ON staging_product_price(eventId)",
        "CREATE INDEX IF NOT EXISTS idx_staging_product_price_product ON staging_product_price(productNumber)",
        "CREATE INDEX IF NOT EXISTS idx_staging_product_price_deal ON staging_product_price(dealNumber, dealYear)",
        "CREATE INDEX IF NOT EXISTS idx_staging_product_price_created ON staging_product_price(recCreationDateTime)",
    ),
)

DATASET_SPECS: Tuple[DatasetSpec, ...] = (
    CPP_SPEC, DEAL_SPEC, REG_SPEC, ZONE_SPEC, STAGING_SPEC)
SPECS_BY_KEY = {spec.key: spec for spec in DATASET_SPECS}
DATASET_KEYS = tuple(spec.key for spec in DATASET_SPECS)
