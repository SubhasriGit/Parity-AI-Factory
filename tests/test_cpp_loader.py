# pyright: reportMissingImports=false
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from init_database import initialize_database
from load_cpp_snapshot_to_db import load_snapshots
from cpp_datasets import DATASET_SPECS


def write_csv(path: Path, columns: tuple, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)
    return path


def fixture_paths(root: Path) -> dict:
    base_values = {
        "cpp": {"packetId": "1", "storeNumber": "0035", "header": "{}", "body": "[]", "recCreationDateTime": "2026-08-14 01:00:00", "lastModifiedDateTime": "", "errorMessage": "", "isProcessed": "1"},
        "deal": {"promoProductPriceId": "1", "productNumber": "0000001", "zoneNumber": "9", "zoneType": "OVERRIDE", "dealNumber": "0001", "dealYear": "2026", "dealType": "A", "promoRetailPrice": "1.000", "promoRetailPriceEffectiveDate": "2026-08-14", "promoDealerPrice": "0.500", "promoDealerPriceEffectiveDate": "2026-08-14", "lastModifiedDateTime": "", "recCreationDateTime": "", "promoRetailPriceEndDate": "", "promoDealerPriceEndDate": ""},
        "regular": {"regProductPriceId": "1", "productNumber": "0000001", "zoneNumber": "9", "zoneType": "OVERRIDE", "regularRetailPrice": "2.000", "regularRetailPriceEffectiveDate": "2026-08-14", "regularRetailPriceEndDate": "", "regularDealerPrice": "1.000", "regularDealerPriceEffectiveDate": "2026-08-14", "regularDealerPriceEndDate": "", "lastModifiedDateTime": "", "recCreationDateTime": "", "regularRetailChangeType": "Initial Price", "regularDealerChangeType": "Initial Price"},
        "zone": {"storeNumber": "0035", "zoneNumber": "9", "recCreationDateTime": "2026-08-14"},
        "staging": {"eventId": "e1", "eventType": "ADD", "productNumber": "0000001", "zoneNumber": "9", "zoneType": "OVERRIDE", "eventAction": "CREATE", "dealNumber": "0001", "dealYear": "2026", "dealType": "A", "retailPrice": "1.000", "retailPriceEffectiveDate": "2026-08-14", "retailPriceEndDate": "", "dealerPrice": "0.500", "dealerPriceEffectiveDate": "2026-08-14", "dealerPriceEndDate": "", "rawRecCreationDateTime": "2026-08-14", "recCreationDateTime": "2026-08-14", "retailChangeType": "ADD", "dealerChangeType": "ADD"},
    }
    paths = {}
    for spec in DATASET_SPECS:
        columns = tuple(column for column in spec.columns if not (
            spec.key == "staging" and column == "rowHash"))
        paths[spec.key] = write_csv(
            root / spec.csv_filename, columns, [base_values[spec.key]])
    return paths


def test_load_all_and_repeat_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "analysis.db"
    initialize_database(db)
    paths = fixture_paths(tmp_path / "cpp")

    first = load_snapshots(
        db, paths, [spec.key for spec in DATASET_SPECS], keep_empty_bodies=True)
    second = load_snapshots(
        db, paths, [spec.key for spec in DATASET_SPECS], keep_empty_bodies=True)

    assert first["table_totals"] == {spec.key: 1 for spec in DATASET_SPECS}
    assert second["datasets"]["cpp"]["ignoredExistingRows"] == 1
    assert second["datasets"]["staging"]["ignoredExistingRows"] == 1
    assert second["table_totals"] == first["table_totals"]


def test_missing_column_fails_before_table_refresh(tmp_path: Path) -> None:
    db = tmp_path / "analysis.db"
    initialize_database(db)
    paths = fixture_paths(tmp_path / "cpp")
    load_snapshots(db, paths, ["deal"])
    bad = tmp_path / "bad.csv"
    write_csv(bad, tuple(column for column in paths["deal"].read_text(
        encoding="utf-8-sig").splitlines()[0].split(",") if column != "dealYear"), [])
    paths["deal"] = bad

    with pytest.raises(ValueError, match="missing expected columns"):
        load_snapshots(db, paths, ["deal"])
    connection = sqlite3.connect(str(db))
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM deal_price_master").fetchone()[0] == 1
    finally:
        connection.close()


def test_replace_creates_backup_and_empty_body_is_skipped_by_default(tmp_path: Path) -> None:
    db = tmp_path / "analysis.db"
    initialize_database(db)
    paths = fixture_paths(tmp_path / "cpp")
    load_snapshots(db, paths, ["cpp"], keep_empty_bodies=True)

    result = load_snapshots(
        db, paths, ["cpp"], replace=True, keep_empty_bodies=False)

    assert result["backup"]
    assert Path(result["backup"]).exists()
    assert result["datasets"]["cpp"]["emptyBodyRows"] == 1
    assert result["table_totals"]["cpp"] == 0
