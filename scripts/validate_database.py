"""Read-only validation for the canonical PM000003 SQLite schema."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Sequence

try:
    from .cpp_datasets import DATASET_SPECS
except ImportError:  # Direct script execution from scripts/.
    from cpp_datasets import DATASET_SPECS

SCHEMA_VERSION = 1
REQUIRED_TABLE_COLUMNS: Dict[str, Sequence[str]] = {
    "_metadata": ("key", "value"),
    "mismatch_input": ("row_id", "day", "direction", "store", "offering_number", "deal_number", "price_type", "effective_date", "dealer_cost_price", "retail_price", "casting_price", "timestamp_utc", "message_id"),
    "mismatch_verdict": ("row_id", "classification", "kd_code", "confidence", "hypothesis", "supporting_evidence", "missing_evidence"),
    "cpp_data": ("STORE_NUMBER", "PRODUCT_NUMBER", "PRICE_NAME", "PRICE_TYPE", "DEAL_NUMBER", "PRICE", "EFFECTIVE_DATE", "SNAPSHOT_DAY", "Comment"),
}
for spec in DATASET_SPECS:
    REQUIRED_TABLE_COLUMNS[spec.table] = spec.columns

REQUIRED_INDEXES = {
    "idx_cpp_price_packets_store",
    "idx_cpp_price_packets_created",
    "idx_deal_price_master_product",
    "idx_deal_price_master_deal",
    "idx_deal_price_master_zone",
    "idx_regular_price_master_product",
    "idx_regular_price_master_zone",
    "idx_zone_store_relation_store",
    "idx_zone_store_relation_zone",
    "idx_staging_product_price_row_hash",
    "idx_staging_product_price_event",
    "idx_staging_product_price_product",
    "idx_staging_product_price_deal",
    "idx_staging_product_price_created",
    "ix_mi_key",
    "ix_mi_dir",
    "ix_mi_day",
    "ix_cpp_data_key",
    "ix_cpp_data_day_key",
    "ix_cpp_data_prod",
}


def validate_database(db_path: Path) -> dict:
    problems: List[str] = []
    if not db_path.exists():
        return {"database": str(db_path), "valid": False, "problems": ["database does not exist"]}
    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            problems.append(
                f"schema version {version}; expected {SCHEMA_VERSION}")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        indexes = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )}
        table_details = {}
        for table, expected in REQUIRED_TABLE_COLUMNS.items():
            if table not in tables:
                problems.append(f"missing table {table}")
                table_details[table] = {"exists": False}
                continue
            actual = tuple(row[1] for row in connection.execute(
                f"PRAGMA table_info({table})"))
            expected_tuple = tuple(expected)
            missing = sorted(set(expected_tuple) - set(actual))
            extra = sorted(set(actual) - set(expected_tuple))
            if missing or extra:
                problems.append(
                    f"table {table}: missing={missing}, unexpected={extra}, expected order={list(expected_tuple)}, actual order={list(actual)}")
            table_details[table] = {
                "exists": True,
                "columns": list(actual),
                "row_count": int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]),
            }
        missing_indexes = sorted(REQUIRED_INDEXES - indexes)
        if missing_indexes:
            problems.append(f"missing indexes: {missing_indexes}")
        metadata_version = connection.execute(
            "SELECT value FROM _metadata WHERE key='schema.version'"
        ).fetchone() if "_metadata" in tables else None
        if metadata_version is None or metadata_version[0] != str(SCHEMA_VERSION):
            problems.append("_metadata schema.version is missing or incorrect")
        return {
            "database": str(db_path),
            "valid": not problems,
            "schema_version": version,
            "problems": problems,
            "tables": table_details,
            "required_index_count": len(REQUIRED_INDEXES),
            "present_index_count": len(REQUIRED_INDEXES & indexes),
        }
    finally:
        connection.close()


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True,
                        help="SQLite database path")
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    result = validate_database(args.db.resolve())
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
