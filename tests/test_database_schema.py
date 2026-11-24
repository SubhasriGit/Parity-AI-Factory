from __future__ import annotations

import importlib.util
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cpp_datasets = load_module("project1_cpp_datasets",
                           ROOT / "scripts" / "cpp_datasets.py")
init_database = load_module(
    "project1_init_database", ROOT / "scripts" / "init_database.py")
validate_database_module = load_module(
    "project1_validate_database", ROOT / "scripts" / "validate_database.py")

DATASET_SPECS = cpp_datasets.DATASET_SPECS
initialize_database_fn = init_database.initialize_database
REQUIRED_INDEXES = validate_database_module.REQUIRED_INDEXES
validate_database_fn = validate_database_module.validate_database


def test_fresh_database_has_exact_canonical_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    result = initialize_database_fn(db_path)

    assert result["created"] is True
    assert result["schema_version"] == 1
    assert result["table_count"] == 9
    assert result["index_count"] == 20

    validation = validate_database_fn(db_path)
    assert validation["valid"] is True
    assert validation["problems"] == []
    assert validation["present_index_count"] == len(REQUIRED_INDEXES)


def test_repeated_initialization_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "repeat.db"
    first = initialize_database_fn(db_path)
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute(
            "INSERT INTO _metadata (key, value) VALUES ('preserved.key', 'preserved.value')"
        )
        connection.commit()
    finally:
        connection.close()

    second = initialize_database_fn(db_path)
    validation = validate_database_fn(db_path)
    connection = sqlite3.connect(str(db_path))
    try:
        preserved = connection.execute(
            "SELECT value FROM _metadata WHERE key = 'preserved.key'"
        ).fetchone()
    finally:
        connection.close()

    assert first["created"] is True
    assert second["created"] is False
    assert preserved == ("preserved.value",)
    assert validation["valid"] is True


def test_dataset_registry_matches_database_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    initialize_database_fn(db_path)
    connection = sqlite3.connect(str(db_path))
    try:
        for spec in DATASET_SPECS:
            actual = tuple(row[1] for row in connection.execute(
                f"PRAGMA table_info({spec.table})"))
            assert actual == spec.columns
    finally:
        connection.close()


def test_regular_price_master_has_no_unused_row_hash(tmp_path: Path) -> None:
    db_path = tmp_path / "regular.db"
    initialize_database_fn(db_path)
    connection = sqlite3.connect(str(db_path))
    try:
        columns = [row[1] for row in connection.execute(
            "PRAGMA table_info(regular_price_master)")]
    finally:
        connection.close()

    assert "rowHash" not in columns
    assert "regularDealerChangeType" in columns


def test_initializer_rejects_incompatible_schema_version(tmp_path: Path) -> None:
    db_path = tmp_path / "incompatible.db"
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA user_version = 99")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="incompatible"):
        initialize_database_fn(db_path)


def test_database_validator_cli_exits_nonzero_for_missing_database(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_database.py"),
         "--db", str(tmp_path / "missing.db")],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert '"valid": false' in completed.stdout
