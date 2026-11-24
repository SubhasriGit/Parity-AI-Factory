"""Migrate explicitly mapped IMS snapshot tables into the canonical database."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STORE_RE = re.compile(r"^\d{4}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BATCH_SIZE = 2000
MINIMUM_COLUMNS = ("PRODUCT_NUMBER", "PRICE_NAME", "PRICE_TYPE",
                   "DEAL_NUMBER", "PRICE", "EFFECTIVE_DATE")


def quote(identifier: str) -> str:
    if not IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Invalid SQLite identifier: {identifier}")
    return f'"{identifier}"'


def normalize_day(value: str) -> str:
    if not DATE_RE.match(value):
        raise ValueError(f"snapshot day must be ISO YYYY-MM-DD, got {value!r}")
    datetime.strptime(value, "%Y-%m-%d")
    return value


def load_day_map(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("mappings", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError(
            "Day mapping must be a list or an object with a 'mappings' list")
    for entry in entries:
        required = {"source_table", "store", "snapshot_day"}
        missing = required - set(entry)
        if missing:
            raise ValueError(f"Day mapping entry missing {sorted(missing)}")
        if not STORE_RE.match(str(entry["store"])):
            raise ValueError(
                f"Store must contain exactly four digits: {entry['store']}")
        entry["store"] = str(entry["store"])
        entry["snapshot_day"] = normalize_day(str(entry["snapshot_day"]))
        quote(str(entry["source_table"]))
    return entries


def backup_database(path: Path) -> Path:
    project_root = Path(__file__).resolve().parent.parent
    backup_dir = project_root.parents[2].parent / \
        "CPP-Private-Originals" / "runtime-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (
        f"{path.stem}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}{path.suffix}.bak")
    shutil.copy2(path, backup)
    return backup


def table_columns(connection: sqlite3.Connection, table: str) -> list:
    return [(row[1], row[2]) for row in connection.execute(f"PRAGMA table_info({quote(table)})")]


def ensure_target_table(target: sqlite3.Connection, table: str, source_columns: list) -> bool:
    existing = table_columns(target, table)
    if not existing:
        definitions = [f"{quote(name)} {column_type or 'TEXT'}" for name,
                       column_type in source_columns if name != "snapshot_day"]
        definitions.append(f'{quote("snapshot_day")} TEXT NOT NULL')
        target.execute(
            f"CREATE TABLE {quote(table)} ({', '.join(definitions)})")
        target.execute(
            f"CREATE INDEX {quote('ix_' + table + '_lookup')} ON {quote(table)} "
            f"(snapshot_day, PRODUCT_NUMBER, PRICE_NAME, DEAL_NUMBER, PRICE_TYPE)"
        )
        return True
    existing_names = {name for name, _ in existing}
    missing = set(MINIMUM_COLUMNS) - existing_names
    if missing or "snapshot_day" not in existing_names:
        raise ValueError(
            f"Target table {table} lacks canonical columns {sorted(missing | ({'snapshot_day'} - existing_names))}")
    added = False
    for name, column_type in source_columns:
        if name not in existing_names and name != "snapshot_day":
            target.execute(
                f"ALTER TABLE {quote(table)} ADD COLUMN {quote(name)} {column_type or 'TEXT'}")
            added = True
    return added


def existing_day_count(target: sqlite3.Connection, table: str, day: str) -> int:
    return int(target.execute(f"SELECT COUNT(*) FROM {quote(table)} WHERE snapshot_day = ?", [day]).fetchone()[0])


def migrate_mapping(source: sqlite3.Connection, target: sqlite3.Connection, mapping: dict, refresh: bool = False) -> dict:
    source_table = str(mapping["source_table"])
    store = str(mapping["store"])
    day = str(mapping["snapshot_day"])
    target_table = f"mf_data_{store}"
    source_columns = table_columns(source, source_table)
    source_names = [name for name, _ in source_columns]
    missing = set(MINIMUM_COLUMNS) - set(source_names)
    if missing:
        raise ValueError(
            f"Source table {source_table} lacks canonical columns {sorted(missing)}")
    if "snapshot_day" in source_names:
        insert_columns = [
            name for name in source_names if name != "snapshot_day"]
    else:
        insert_columns = source_names

    schema_changed = ensure_target_table(target, target_table, source_columns)
    existing = existing_day_count(target, target_table, day)
    if existing and not refresh:
        source_count = int(source.execute(
            f"SELECT COUNT(*) FROM {quote(source_table)}").fetchone()[0])
        return {"source_table": source_table, "target_table": target_table, "store": store,
                "snapshot_day": day, "status": "SKIPPED", "source_rows": source_count,
                "existing_rows": existing, "inserted_rows": 0, "schema_changed": schema_changed}
    if refresh and existing:
        target.execute(
            f"DELETE FROM {quote(target_table)} WHERE snapshot_day = ?", [day])
        existing = 0

    select_columns = ", ".join(quote(name) for name in insert_columns)
    rows = source.execute(
        f"SELECT {select_columns} FROM {quote(source_table)}")
    target_select_columns = insert_columns + ["snapshot_day"]
    placeholders = ", ".join("?" for _ in target_select_columns)
    insert_sql = f"INSERT INTO {quote(target_table)} ({', '.join(quote(name) for name in target_select_columns)}) VALUES ({placeholders})"
    comparison = " AND ".join(
        f"{quote(name)} IS ?" for name in insert_columns) + " AND snapshot_day = ?"
    insert_check = f"SELECT 1 FROM {quote(target_table)} WHERE {comparison} LIMIT 1"
    inserted = ignored = source_rows = 0
    batch = []
    for row in rows:
        source_rows += 1
        values = list(row) + [day]
        if target.execute(insert_check, values).fetchone() is not None:
            ignored += 1
            continue
        batch.append(tuple(values))
        if len(batch) >= BATCH_SIZE:
            target.executemany(insert_sql, batch)
            inserted += len(batch)
            batch.clear()
    if batch:
        target.executemany(insert_sql, batch)
        inserted += len(batch)
    target_count = existing_day_count(target, target_table, day)
    if target_count != source_rows:
        raise RuntimeError(
            f"IMS parity failed for {source_table} -> {target_table}/{day}: source={source_rows}, target={target_count}"
        )
    return {"source_table": source_table, "target_table": target_table, "store": store,
            "snapshot_day": day, "status": "LOADED", "source_rows": source_rows,
            "existing_rows": existing, "inserted_rows": inserted, "ignored_rows": ignored,
            "target_rows": target_count, "schema_changed": schema_changed}


def migrate_snapshots(source_path: Path, target_path: Path, day_map_path: Path, refresh: bool = False,
                      store_filter: Optional[list] = None) -> dict:
    if not source_path.exists():
        raise FileNotFoundError(
            f"Source database does not exist: {source_path}")
    if not target_path.exists():
        raise FileNotFoundError(
            f"Target database does not exist: {target_path}")
    mappings = load_day_map(day_map_path)
    stores = set(store_filter or [])
    if stores:
        mappings = [
            mapping for mapping in mappings if mapping["store"] in stores]
    if not mappings:
        raise ValueError("No IMS mappings selected")

    source = sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True)
    target = sqlite3.connect(str(target_path))
    backup = None
    results = []
    try:
        source_tables = {row[0] for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for mapping in mappings:
            if mapping["source_table"] not in source_tables:
                raise ValueError(
                    f"Mapped source table does not exist: {mapping['source_table']}")
        target_tables_before = {row[0] for row in target.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if refresh or any(f"mf_data_{mapping['store']}" not in target_tables_before for mapping in mappings):
            backup = str(backup_database(target_path))
        target.execute("BEGIN")
        for mapping in mappings:
            results.append(migrate_mapping(source, target, mapping, refresh))
        target.commit()
        metadata = {
            f"ims_migration.{mapping['store']}.{mapping['snapshot_day']}": json.dumps(result, sort_keys=True)
            for mapping, result in zip(mappings, results)
        }
        target.executemany(
            "INSERT INTO _metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            list(metadata.items()),
        )
        target.commit()
        return {"source": str(source_path), "database": str(target_path), "backup": backup, "mappings": results}
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--day-map", type=Path, required=True)
    parser.add_argument("--store", action="append", dest="stores")
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    try:
        print(json.dumps(migrate_snapshots(args.source.resolve(), args.db.resolve(
        ), args.day_map.resolve(), args.refresh, args.stores), indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
