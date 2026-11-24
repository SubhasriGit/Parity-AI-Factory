"""Stages 0.2-3: parse dataset files and store raw rows in the local DB.

Raw values are stored exactly as parsed (TEXT). Typing/normalisation happens
only right before comparison, so the raw layer always reflects the source.

Load policies (config/datasets.json -> load_policy):
  replace: delete existing rows then insert (master/snapshot tables)
  append : keep history; rows are de-duplicated on a hash of `dedupe_on`
           columns (default: all mapped columns)
Each file is fingerprinted (SHA-256); re-loading an identical file is skipped
unless --force is given.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .config import Dataset, ProjectContext
from .connectors import get_connector
from .db import Database, q

META_COLUMNS = ["_rid", "_load_id", "_source_file", "_line_no", "_row_hash"]

_max_field = sys.maxsize
while True:
    try:
        csv.field_size_limit(_max_field)
        break
    except OverflowError:
        _max_field = int(_max_field / 10)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class ParseError(Exception):
    pass


def iter_records(dataset: Dataset, path: Path) -> Iterator[tuple]:
    """Yield (line_no, {column: raw_text}) for each record in the file."""
    fmt = dataset.format
    fmt_type = fmt.get("type", "csv")
    encoding = fmt.get("encoding", "utf-8-sig")
    columns = dataset.mapping.get("columns", [])
    extract = fmt.get("extract")
    extract_re = re.compile(extract["pattern"]) if extract else None
    skip_prefixes = tuple(fmt.get("skip_lines_starting_with", []) or [])
    strip_values = fmt.get("strip_values", fmt_type == "fixed_width")

    def finish(line_no: int, raw: Dict[str, Any]) -> Optional[Dict[str, Optional[str]]]:
        if extract_re is not None:
            text = raw.get(extract.get("from_column", ""), "")
            match = extract_re.search(text or "")
            if match is None:
                if extract.get("on_no_match", "skip") == "error":
                    raise ParseError(f"{path.name} line {line_no}: extract pattern did not match")
                if extract.get("on_no_match", "skip") == "skip":
                    return None
            else:
                raw.update({k: v for k, v in match.groupdict().items()})
        record: Dict[str, Optional[str]] = {}
        for col in columns:
            key = col.get("source", col["name"])
            if fmt_type == "fixed_width":
                key = col["name"]
            elif fmt_type == "csv" and fmt.get("header", True) is False:
                key = col["index"]
            value = raw.get(key, col.get("default"))
            if value is not None and not isinstance(value, str):
                value = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            if value is not None and strip_values:
                value = value.strip()
            record[col["name"]] = value
        return record

    if fmt_type == "csv":
        with open(path, "r", encoding=encoding, newline="") as handle:
            for _ in range(int(fmt.get("skip_rows", 0))):
                next(handle, None)
            delimiter = fmt.get("delimiter", ",")
            quotechar = fmt.get("quotechar", '"')
            if fmt.get("header", True) is False:
                reader = csv.reader(handle, delimiter=delimiter, quotechar=quotechar)
                for line_no, row in enumerate(reader, start=1):
                    if not row or (skip_prefixes and row[0].startswith(skip_prefixes)):
                        continue
                    record = finish(line_no, {i: v for i, v in enumerate(row)})
                    if record is not None:
                        yield line_no, record
                return
            reader = csv.DictReader(handle, delimiter=delimiter, quotechar=quotechar)
            headers = [h.strip() if h else h for h in (reader.fieldnames or [])]
            reader.fieldnames = headers
            needed = {c.get("source", c["name"]) for c in columns if c.get("required", True) and "default" not in c}
            if extract:
                needed -= set(extract_re.groupindex.keys())  # type: ignore[union-attr]
                needed.add(extract.get("from_column"))
            missing = sorted(n for n in needed if n not in headers)
            if missing:
                raise ParseError(
                    f"{path.name}: missing column(s) {missing}. File headers: {headers}. "
                    f"Update the mapping 'source' values in {dataset.raw.get('mapping')}."
                )
            for line_no, row in enumerate(reader, start=2):
                if skip_prefixes and str(next(iter(row.values()), "")).startswith(skip_prefixes):
                    continue
                record = finish(line_no, dict(row))
                if record is not None:
                    yield line_no, record
        return

    if fmt_type == "fixed_width":
        with open(path, "r", encoding=encoding, newline="") as handle:
            for _ in range(int(fmt.get("skip_rows", 0))):
                next(handle, None)
            for line_no, line in enumerate(handle, start=1 + int(fmt.get("skip_rows", 0))):
                line = line.rstrip("\r\n")
                if not line.strip() or (skip_prefixes and line.startswith(skip_prefixes)):
                    continue
                raw = {c["name"]: line[int(c["start"]) - 1 : int(c["end"])] for c in columns}
                record = finish(line_no, raw)
                if record is not None:
                    yield line_no, record
        return

    if fmt_type == "jsonl":
        with open(path, "r", encoding=encoding) as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                obj = json.loads(line)
                flat = {c.get("source", c["name"]): _json_path(obj, c.get("source", c["name"])) for c in columns}
                record = finish(line_no, flat)
                if record is not None:
                    yield line_no, record
        return

    raise ParseError(f"Unsupported format type '{fmt_type}'")


def _json_path(obj: Any, path: str) -> Any:
    for part in str(path).split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


# ---------------------------------------------------------------------------
# Raw table management
# ---------------------------------------------------------------------------


def ensure_raw_table(db: Database, dataset: Dataset) -> None:
    table = dataset.raw_table
    if not db.table_exists(table):
        cols = ", ".join(
            [f"{q('_rid')} INTEGER", f"{q('_load_id')} INTEGER", f"{q('_source_file')} TEXT", f"{q('_line_no')} INTEGER", f"{q('_row_hash')} TEXT"]
            + [f"{q(c)} TEXT" for c in dataset.columns]
        )
        db.execute(f"CREATE TABLE {q(table)} ({cols})")
    else:
        existing = set(db.columns(table))
        for column in dataset.columns:
            if column not in existing:
                db.execute(f"ALTER TABLE {q(table)} ADD COLUMN {q(column)} TEXT")
    if dataset.load_policy.get("mode", "replace") == "append":
        db.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {q('ux_' + table + '_hash')} ON {q(table)} ({q('_row_hash')})")
    db.commit()


def _row_hash(record: Dict[str, Optional[str]], columns: List[str]) -> str:
    joined = "\x1f".join("\x00" if record.get(c) is None else str(record.get(c)) for c in columns)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def already_loaded(db: Database, dataset: str, sha: str) -> Optional[dict]:
    row = db.execute(
        "SELECT load_id, source_file, loaded_at, rows_inserted FROM _loads "
        "WHERE dataset = ? AND file_sha256 = ? AND status = 'OK' ORDER BY load_id DESC",
        [dataset, sha],
    ).fetchone()
    if row:
        return {"load_id": row[0], "source_file": row[1], "loaded_at": row[2], "rows_inserted": row[3]}
    return None


def load_dataset(
    ctx: ProjectContext,
    dataset: Dataset,
    files: Optional[List[str]] = None,
    force: bool = False,
    load_batch: Optional[int] = None,
) -> List[dict]:
    db = ctx.db
    connector = get_connector(dataset.name, dataset.connector, ctx.root)
    paths = connector.resolve(files)
    ensure_raw_table(db, dataset)
    policy = dataset.load_policy
    mode = policy.get("mode", "replace")
    dedupe_cols = policy.get("dedupe_on") or dataset.columns
    batch_size = ctx.batch_size
    if load_batch is None:
        load_batch = db.next_id("_loads", "load_batch")

    results: List[dict] = []
    replaced = False
    for path in paths:
        sha = file_sha256(path)
        previous = already_loaded(db, dataset.name, sha)
        if previous and not force:
            results.append(
                {
                    "dataset": dataset.name,
                    "file": str(path),
                    "status": "SKIPPED",
                    "reason": f"identical file already loaded (load_id {previous['load_id']} at {previous['loaded_at']})",
                }
            )
            continue

        load_id = db.next_id("_loads", "load_id")
        rows_read = rows_inserted = 0
        try:
            removed = 0
            if mode == "replace" and not replaced:
                removed = db.count(dataset.raw_table)
                db.execute(f"DELETE FROM {q(dataset.raw_table)}")
                replaced = True
            before = db.count(dataset.raw_table)
            next_rid = db.next_id(dataset.raw_table, "_rid")
            insert_cols = META_COLUMNS + dataset.columns
            buffer: List[list] = []
            for line_no, record in iter_records(dataset, path):
                rows_read += 1
                values = [next_rid, load_id, path.name, line_no, _row_hash(record, dedupe_cols)]
                values.extend(record.get(c) for c in dataset.columns)
                buffer.append(values)
                next_rid += 1
                if len(buffer) >= batch_size:
                    db.insert_rows(dataset.raw_table, insert_cols, buffer, ignore=(mode == "append"))
                    buffer = []
            db.insert_rows(dataset.raw_table, insert_cols, buffer, ignore=(mode == "append"))
            rows_inserted = db.count(dataset.raw_table) - before
            db.execute(
                "INSERT INTO _loads (load_id, load_batch, dataset, source_file, file_sha256, file_size, rows_read, "
                "rows_inserted, rows_skipped, policy, loaded_at, status, message) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    load_id, load_batch, dataset.name, str(path), sha, path.stat().st_size, rows_read,
                    rows_inserted, rows_read - rows_inserted, mode, utc_now(), "OK",
                    f"removed {removed} previous rows" if mode == "replace" else "",
                ],
            )
            db.set_meta(f"{dataset.name}.last_load_id", load_id)
            db.set_meta(f"{dataset.name}.last_source_file", str(path))
            db.set_meta(f"{dataset.name}.last_loaded_at", utc_now())
            db.commit()
        except Exception:
            db.rollback()
            raise
        results.append(
            {
                "dataset": dataset.name,
                "file": str(path),
                "status": "LOADED",
                "policy": mode,
                "load_id": load_id,
                "rows_read": rows_read,
                "rows_inserted": rows_inserted,
                "rows_already_present": rows_read - rows_inserted,
                "rows_removed_before_load": removed,
                "table_total": db.count(dataset.raw_table),
            }
        )
    return results
