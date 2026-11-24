# Database Schema

## Phase 1 Contract

The executable schema is `schema/001_create_core_schema.sql`. `scripts/init_database.py` creates a missing database or idempotently verifies an existing compatible database. `scripts/validate_database.py` validates it read-only.

Current schema version: `1` (`PRAGMA user_version` and `_metadata.schema.version`).

## Core Tables

- `_metadata`: schema and future load/run metadata
- `cpp_price_packets`: CPP packet history keyed by `packetId`
- `deal_price_master`: refreshed promotional master snapshot
- `regular_price_master`: refreshed regular master snapshot; no unused `rowHash`
- `zone_store_relation`: refreshed store/zone relationships
- `staging_product_price`: append history deduplicated by `rowHash`
- `mismatch_input`: current parsed mismatch population
- `mismatch_verdict`: exactly one current verdict per mismatch row
- `cpp_data`: canonical rows rebuilt from CPP packet JSON, including `SNAPSHOT_DAY`

## IMS Table Template

`schema/002_create_mf_template.sql` defines one validated four-digit store table, `mf_data_<store>`, preserving source columns and requiring `snapshot_day`.

IMS scripts must supply an explicit table-to-ISO-day mapping. No implementation may infer an ambiguous suffix.

## Dataset Registry

`scripts/cpp_datasets.py` is the source for CPP CSV filenames, ordered columns, insert semantics, table DDL, indexes, and refresh policy.

## Initialization

```powershell
python scripts/init_database.py --db output/pm000003.db
python scripts/validate_database.py --db output/pm000003.db
```

Initialization is idempotent. It rejects a nonzero incompatible `user_version`; it does not delete existing data.

## Validation

Validation fails on:

- a missing database;
- incorrect schema version;
- missing or incorrectly shaped tables;
- unexpected or missing mapped columns;
- missing required indexes;
- missing or incorrect `_metadata.schema.version`.
