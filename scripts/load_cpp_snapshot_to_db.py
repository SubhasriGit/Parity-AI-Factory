"""Load validated PM000003 CPP snapshot CSVs into SQLite."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

try:
    from .cpp_datasets import DATASET_KEYS, DATASET_SPECS, SPECS_BY_KEY, DatasetSpec
except ImportError:
    from cpp_datasets import DATASET_KEYS, DATASET_SPECS, SPECS_BY_KEY, DatasetSpec

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "pm000003_mismatch_analysis.db"
DEFAULT_CSV_DIR = ROOT / "cpp_data"
BATCH_SIZE = 2000
SUSPECTED_TRUNCATION_LENGTHS = {65535, 1048576}
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def normalize_nullable(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return None if not stripped or stripped.upper() == "NULL" else value


def parse_int(value: Optional[str]) -> Optional[int]:
    normalized = normalize_nullable(value)
    if normalized is None:
        return None
    try:
        return int(normalized.strip())
    except ValueError:
        return None


def staging_hash(values: list) -> str:
    payload = "\x1f".join("<NULL>" if value is None else str(value)
                          for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require_columns(csv_path: Path, columns: Iterable[str]) -> None:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        headers = next(reader, [])
    missing = sorted(set(columns) - set(headers))
    if missing:
        raise ValueError(
            f"{csv_path}: missing expected columns {missing}; table was not changed")


def read_rows(csv_path: Path) -> Iterable[dict]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def read_balanced_json(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError(f"Unterminated {opening}...{closing} token")


def parse_unquoted_cpp_row(line: str) -> Optional[dict]:
    line = line.rstrip("\r\n")
    first = line.find(",")
    second = line.find(",", first + 1) if first >= 0 else -1
    if first < 0 or second < 0:
        return None
    packet_id = line[:first]
    store = line[first + 1:second]
    cursor = second + 1
    if cursor < len(line) and line[cursor] == "{":
        header_end = read_balanced_json(line, cursor, "{", "}")
        header = line[cursor:header_end]
    else:
        header_end = cursor
        header = ""
    if header_end >= len(line) or line[header_end] != ",":
        return None
    body_start = header_end + 1
    if body_start < len(line) and line[body_start] == "[":
        body_end = read_balanced_json(line, body_start, "[", "]")
        body = line[body_start:body_end]
    else:
        body_end = body_start
        body = ""
    tail = line[body_end +
                1:] if body_end < len(line) and line[body_end] == "," else ""
    parts = (tail.split(",", 3) + ["", "", "", ""])[:4]
    return {
        "packetId": packet_id.strip(), "storeNumber": store.strip(), "header": header,
        "body": body, "recCreationDateTime": parts[0], "lastModifiedDateTime": parts[1],
        "errorMessage": parts[2], "isProcessed": parts[3],
    }


def cpp_rows(csv_path: Path) -> Iterable[dict]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        handle.readline()
        second = handle.readline()
    if second and len(second.split(",", 2)) == 3 and second.split(",", 2)[2].lstrip().startswith("{"):
        with csv_path.open("r", encoding="utf-8-sig") as handle:
            next(handle, None)
            for line in handle:
                parsed = parse_unquoted_cpp_row(line)
                if parsed is not None:
                    yield parsed
    else:
        yield from read_rows(csv_path)


def insert_batch(connection: sqlite3.Connection, spec: DatasetSpec, rows: list) -> int:
    if not rows:
        return 0
    before = connection.total_changes
    connection.executemany(spec.insert_sql, rows)
    return connection.total_changes - before


def load_cpp(csv_path: Path, connection: sqlite3.Connection, keep_empty: bool) -> dict:
    stats = {"csvRows": 0, "insertedRows": 0, "ignoredExistingRows": 0,
             "skippedRows": 0, "emptyBodyRows": 0, "truncatedBodyRows": 0}
    batch = []
    for row in cpp_rows(csv_path):
        stats["csvRows"] += 1
        packet_id = parse_int(row.get("packetId"))
        if packet_id is None:
            stats["skippedRows"] += 1
            continue
        body = row.get("body") or ""
        if not keep_empty and body.strip() in ("", "[]"):
            stats["emptyBodyRows"] += 1
            continue
        if len(body) in SUSPECTED_TRUNCATION_LENGTHS:
            stats["truncatedBodyRows"] += 1
        batch.append((packet_id, (row.get("storeNumber") or "").strip(), row.get("header"), body,
                      normalize_nullable(row.get("recCreationDateTime")), normalize_nullable(
                          row.get("lastModifiedDateTime")),
                      normalize_nullable(row.get("errorMessage")), parse_int(row.get("isProcessed"))))
        if len(batch) >= BATCH_SIZE:
            stats["insertedRows"] += insert_batch(
                connection, SPECS_BY_KEY["cpp"], batch)
            batch.clear()
    stats["insertedRows"] += insert_batch(connection,
                                          SPECS_BY_KEY["cpp"], batch)
    kept = stats["csvRows"] - stats["skippedRows"] - stats["emptyBodyRows"]
    stats["ignoredExistingRows"] = kept - stats["insertedRows"]
    return stats


def load_int_pk(csv_path: Path, connection: sqlite3.Connection, spec: DatasetSpec) -> dict:
    stats = {"csvRows": 0, "insertedRows": 0,
             "ignoredExistingRows": 0, "skippedRows": 0}
    batch = []
    for row in read_rows(csv_path):
        stats["csvRows"] += 1
        primary = parse_int(row.get(spec.pk_col or ""))
        if primary is None:
            stats["skippedRows"] += 1
            continue
        values = [primary if column == spec.pk_col else normalize_nullable(
            row.get(column)) for column in spec.columns]
        batch.append(tuple(values))
        if len(batch) >= BATCH_SIZE:
            stats["insertedRows"] += insert_batch(connection, spec, batch)
            batch.clear()
    stats["insertedRows"] += insert_batch(connection, spec, batch)
    stats["ignoredExistingRows"] = stats["csvRows"] - \
        stats["skippedRows"] - stats["insertedRows"]
    return stats


def load_zone(csv_path: Path, connection: sqlite3.Connection, spec: DatasetSpec) -> dict:
    stats = {"csvRows": 0, "insertedRows": 0,
             "ignoredExistingRows": 0, "skippedRows": 0}
    batch = []
    for row in read_rows(csv_path):
        stats["csvRows"] += 1
        store = (row.get("storeNumber") or "").strip()
        zone = (row.get("zoneNumber") or "").strip()
        if not store or not zone:
            stats["skippedRows"] += 1
            continue
        batch.append((store, zone, normalize_nullable(
            row.get("recCreationDateTime"))))
        if len(batch) >= BATCH_SIZE:
            stats["insertedRows"] += insert_batch(connection, spec, batch)
            batch.clear()
    stats["insertedRows"] += insert_batch(connection, spec, batch)
    stats["ignoredExistingRows"] = stats["csvRows"] - \
        stats["skippedRows"] - stats["insertedRows"]
    return stats


def load_staging(csv_path: Path, connection: sqlite3.Connection, spec: DatasetSpec) -> dict:
    stats = {"csvRows": 0, "insertedRows": 0,
             "ignoredExistingRows": 0, "skippedRows": 0}
    batch = []
    base_columns = tuple(
        column for column in spec.columns if column != "rowHash")
    for row in read_rows(csv_path):
        stats["csvRows"] += 1
        event_id = (row.get("eventId") or "").strip()
        if not event_id:
            stats["skippedRows"] += 1
            continue
        values = [event_id if column == "eventId" else normalize_nullable(
            row.get(column)) for column in base_columns]
        values.append(staging_hash(values))
        batch.append(tuple(values))
        if len(batch) >= BATCH_SIZE:
            stats["insertedRows"] += insert_batch(connection, spec, batch)
            batch.clear()
    stats["insertedRows"] += insert_batch(connection, spec, batch)
    stats["ignoredExistingRows"] = stats["csvRows"] - \
        stats["skippedRows"] - stats["insertedRows"]
    return stats


def dispatch(spec: DatasetSpec, path: Path, connection: sqlite3.Connection, keep_empty: bool) -> dict:
    if spec.key == "cpp":
        return load_cpp(path, connection, keep_empty)
    if spec.key == "staging":
        return load_staging(path, connection, spec)
    if spec.key == "zone":
        return load_zone(path, connection, spec)
    if spec.pk_col:
        return load_int_pk(path, connection, spec)
    raise ValueError(f"No loader for dataset {spec.key}")


def record_metadata(connection: sqlite3.Connection, spec: DatasetSpec, path: Path, stats: dict) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entries = {f"{spec.table}.sourceCsv": str(
        path.resolve()), f"{spec.table}.loadedAtUtc": now}
    entries.update({f"{spec.table}.{key}": str(value)
                   for key, value in stats.items()})
    connection.executemany(
        "INSERT INTO _metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        list(entries.items()),
    )


def backup_database(path: Path) -> Path:
    backup = path.with_name(
        f"{path.stem}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}{path.suffix}.bak")
    shutil.copy2(path, backup)
    return backup


def load_snapshots(db_path: Path, csv_paths: Dict[str, Path], enabled: Iterable[str], replace: bool = False,
                   keep_empty_bodies: bool = False) -> dict:
    enabled_set = set(enabled)
    selected = [spec for spec in DATASET_SPECS if spec.key in enabled_set]
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database does not exist: {db_path}; run init_database.py first")
    for spec in selected:
        path = csv_paths[spec.key]
        if not path.exists():
            raise FileNotFoundError(
                f"CSV for {spec.key} does not exist: {path}")
        columns = (column for column in spec.columns if not (
            spec.key == "staging" and column == "rowHash"))
        require_columns(path, columns)

    backup = str(backup_database(db_path)) if replace else None
    connection = sqlite3.connect(str(db_path))
    results = {}
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        for spec in selected:
            connection.execute(spec.create_sql)
            for sql in spec.index_sqls:
                connection.execute(sql)
        for spec in selected:
            path = csv_paths[spec.key]
            removed = 0
            if replace or spec.truncate_before_load:
                removed = connection.execute(
                    f"DELETE FROM {spec.table}").rowcount or 0
            connection.execute("SAVEPOINT dataset_load")
            try:
                stats = dispatch(spec, path, connection, keep_empty_bodies)
                stats["removedBeforeLoad"] = removed
                record_metadata(connection, spec, path, stats)
                connection.execute("RELEASE SAVEPOINT dataset_load")
            except Exception:
                connection.execute("ROLLBACK TO SAVEPOINT dataset_load")
                connection.execute("RELEASE SAVEPOINT dataset_load")
                raise
            connection.commit()
            results[spec.key] = {"csv": str(path), **stats}
        totals = {spec.key: connection.execute(
            f"SELECT COUNT(*) FROM {spec.table}").fetchone()[0] for spec in selected}
        return {"database": str(db_path), "backup": backup, "datasets": results, "table_totals": totals}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    parser.add_argument("--only", action="append", choices=DATASET_KEYS)
    parser.add_argument("--replace", action="store_true",
                        help="Destructive reload; creates a database backup first")
    parser.add_argument("--keep-empty-bodies", action="store_true")
    for spec in DATASET_SPECS:
        parser.add_argument(f"--{spec.key}-csv", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    paths = {spec.key: getattr(args, f"{spec.key}_csv") or (
        args.csv_dir / spec.csv_filename) for spec in DATASET_SPECS}
    try:
        result = load_snapshots(args.db.resolve(
        ), paths, args.only or DATASET_KEYS, args.replace, args.keep_empty_bodies)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
