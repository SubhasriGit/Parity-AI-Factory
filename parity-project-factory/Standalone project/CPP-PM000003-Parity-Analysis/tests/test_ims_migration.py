from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import conftest  # noqa: F401
from init_database import initialize_database
from migrate_ims_snapshot_to_db import migrate_snapshots, load_day_map


def create_source(path: Path, table: str = "mf_source_0035") -> None:
    connection = sqlite3.connect(str(path))
    try:
        connection.execute(f'''CREATE TABLE {table} (
            STORE_ID TEXT, PRODUCT_NUMBER TEXT, PRICE_NAME TEXT, PRICE_TYPE TEXT,
            DEAL_NUMBER TEXT, PRICE TEXT, EFFECTIVE_DATE TEXT, Comment TEXT,
            original_source TEXT)''')
        connection.executemany(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?,?)",
            [("0035", "0000001", "Promo", "RETAIL", "0001", "1.000", "2026-08-14", "x", "s1"),
             ("0035", "0000001", "Promo", "DEALER", "0001", "0.500", "2026-08-14", "x", "s2")],
        )
        connection.commit()
    finally:
        connection.close()


def day_map(path: Path) -> Path:
    path.write_text(json.dumps({"mappings": [
                    {"source_table": "mf_source_0035", "store": "0035", "snapshot_day": "2026-08-14"}]}), encoding="utf-8")
    return path


def test_migrate_and_repeat_are_idempotent(tmp_path: Path) -> None:
    source, target, mapping = tmp_path / "source.db", tmp_path / \
        "target.db", tmp_path / "map.json"
    create_source(source)
    initialize_database(target)
    day_map(mapping)

    first = migrate_snapshots(source, target, mapping)
    second = migrate_snapshots(source, target, mapping)

    assert first["mappings"][0]["inserted_rows"] == 2
    assert second["mappings"][0]["status"] == "SKIPPED"
    connection = sqlite3.connect(str(target))
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM mf_data_0035 WHERE snapshot_day='2026-08-14'").fetchone()[0] == 2
        columns = {row[1] for row in connection.execute(
            "PRAGMA table_info(mf_data_0035)")}
        assert "original_source" in columns
        assert "snapshot_day" in columns
    finally:
        connection.close()


def test_explicit_day_map_is_required(tmp_path: Path) -> None:
    mapping = tmp_path / "bad.json"
    mapping.write_text(json.dumps(
        {"mappings": [{"source_table": "x", "store": "0035"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="snapshot_day"):
        load_day_map(mapping)

    mapping.write_text(json.dumps({"mappings": [
                       {"source_table": "x", "store": "35", "snapshot_day": "2026-08-14"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="four digits"):
        load_day_map(mapping)


def test_refresh_creates_backup_and_replaces_only_named_day(tmp_path: Path) -> None:
    source, target, mapping = tmp_path / "source.db", tmp_path / \
        "target.db", tmp_path / "map.json"
    create_source(source)
    initialize_database(target)
    day_map(mapping)
    migrate_snapshots(source, target, mapping)

    connection = sqlite3.connect(str(target))
    try:
        connection.execute("INSERT INTO mf_data_0035 VALUES (?,?,?,?,?,?,?,?,?,?)", [
                           "0035", "0009999", "Promo", "RETAIL", "0001", "9.000", "2026-08-15", "other", "old", "2026-08-15"])
        connection.commit()
    finally:
        connection.close()

    result = migrate_snapshots(source, target, mapping, refresh=True)
    assert result["backup"] and Path(result["backup"]).exists()
    connection = sqlite3.connect(str(target))
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM mf_data_0035 WHERE snapshot_day='2026-08-14'").fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM mf_data_0035 WHERE snapshot_day='2026-08-15'").fetchone()[0] == 1
    finally:
        connection.close()


def test_missing_canonical_source_column_rolls_back(tmp_path: Path) -> None:
    source, target, mapping = tmp_path / "bad_source.db", tmp_path / \
        "target.db", tmp_path / "map.json"
    connection = sqlite3.connect(str(source))
    connection.execute(
        "CREATE TABLE mf_source_0035 (STORE_ID TEXT, PRODUCT_NUMBER TEXT)")
    connection.close()
    initialize_database(target)
    day_map(mapping)

    with pytest.raises(ValueError, match="canonical columns"):
        migrate_snapshots(source, target, mapping)
    connection = sqlite3.connect(str(target))
    try:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mf_data_0035'").fetchone() is None
    finally:
        connection.close()
