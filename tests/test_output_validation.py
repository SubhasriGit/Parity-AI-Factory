# pyright: reportMissingImports=false, reportUnusedImport=false
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from openpyxl import load_workbook

import conftest  # noqa: F401
from init_database import initialize_database
from review_and_report import write_workbook
from validate_outputs import validate
from consolidated_report import consolidate
from pm000003_mismatch_report import validate_config


def create_report_db(path: Path) -> Path:
    initialize_database(path)
    connection = sqlite3.connect(str(path))
    cursor = connection.execute(
        "INSERT INTO mismatch_input(day,direction,store,offering_number,deal_number,price_type,effective_date,dealer_cost_price,retail_price,casting_price,timestamp_utc,message_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ["2026-08-14", "CDCS_missing_in_CPP", "0035", "0000001", "0001", "PROMO",
            "2026-08-14", "0.500", "1.000", "0.000", "2026-08-14 10:00:00", "m1"],
    )
    connection.execute("INSERT INTO mismatch_verdict VALUES (?,?,?,?,?,?,?)", [
                       cursor.lastrowid, "POTENTIAL_ISSUE", "KD-2?", 0.45, "candidate", "{}", '["priceChangeEvent"]'])
    connection.commit()
    connection.close()
    return path


def test_output_validation_reconciles_db_and_workbook(tmp_path: Path) -> None:
    db = create_report_db(tmp_path / "analysis.db")
    report = tmp_path / "report.xlsx"
    write_workbook(db, report, final_review=True)
    assert validate(db, report)["valid"] is True


def test_consolidation_accepts_only_explicit_valid_reports(tmp_path: Path) -> None:
    db = create_report_db(tmp_path / "analysis.db")
    first = tmp_path / "one.xlsx"
    second = tmp_path / "two.xlsx"
    write_workbook(db, first, final_review=True)
    write_workbook(db, second, final_review=True)
    output = tmp_path / "consolidated.xlsx"
    result = consolidate([first, second], output)
    workbook = load_workbook(output, read_only=True)
    assert result["reports"] == 2
    assert workbook.sheetnames == [
        "Overview", "Daily Summary", "Issues to Review"]


def test_config_rejects_duplicate_directions_and_unknown_columns() -> None:
    duplicate = {"csv_inputs": [
        {"comparisonDirection": "CDCS_missing_in_CPP", "csvPath": "a.csv"},
        {"comparisonDirection": "CDCS_missing_in_CPP", "csvPath": "b.csv"}],
        "priceTypeRules": [{"rule": "dealNumber != 0", "priceType": "PROMO"}],
        "outputPath": "x.xlsx"}
    with pytest.raises(ValueError, match="exactly"):
        validate_config(duplicate)
    unknown = dict(duplicate)
    unknown["csv_inputs"] = [duplicate["csv_inputs"][0], {
        "comparisonDirection": "CPP_missing_in_CDCS", "csvPath": "b.csv"}]
    unknown["detailColumns"] = ["not_a_column"]
    with pytest.raises(ValueError, match="unknown columns"):
        validate_config(unknown)
