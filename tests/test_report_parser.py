# pyright: reportMissingImports=false
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from openpyxl import load_workbook

from init_database import initialize_database
from pm000003_mismatch_report import parse_inputs, pair_rows, run


def message(deal: str, offering: str, retail: str, dealer: str, effective: str = "2026-08-14") -> str:
    return f"PromoDealPriceDto(dealNumber={deal}, offeringNumber={offering}, effectiveDate={effective}, dealerCostPrice={dealer}, retailPrice={retail}, castingPrice=0)"


def write_input(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["Timestamp", "Store", "Message", "Message Id"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def inputs(tmp_path: Path) -> list[dict]:
    first = write_input(tmp_path / "cdcs.csv", [
        {"Timestamp": "August 14, 2026 10:00:00", "Store": "35", "Message": message(
            "1", "1", "1.000", "0.500") + " " + message("2", "2", "2.000", "1.000"), "Message Id": "m1"},
        {"Timestamp": "August 14, 2026 11:00:00", "Store": "64",
            "Message": "malformed", "Message Id": "bad"},
    ])
    second = write_input(tmp_path / "cpp.csv", [
        {"Timestamp": "August 14, 2026 10:05:00", "Store": "35",
            "Message": message("1", "1", "1.500", "0.500"), "Message Id": "m2"},
    ])
    return [
        {"comparisonDirection": "CDCS_missing_in_CPP", "csvPath": str(first)},
        {"comparisonDirection": "CPP_missing_in_CDCS", "csvPath": str(second)},
    ]


def test_multiple_dtos_malformed_accounting_and_pairing(tmp_path: Path) -> None:
    rows, metrics = parse_inputs(inputs(tmp_path), r"PromoDealPriceDto\(dealNumber=(?P<dealNumber>[^,)]*), offeringNumber=(?P<offeringNumber>[^,)]*), effectiveDate=(?P<effectiveDate>[^,)]*), dealerCostPrice=(?P<dealerCostPrice>[^,)]*), retailPrice=(?P<retailPrice>[^,)]*), castingPrice=(?P<castingPrice>[^)]*)\)", [
                                 {"rule": "dealNumber != 0", "priceType": "PROMO"}])
    pairs = pair_rows(rows)

    assert metrics["parsed_rows"] == 3
    assert metrics["malformed_rows"] == 1
    assert rows[0].store == "0035"
    assert rows[0].offering_number == "0000001"
    assert sum(pair["type"] == "PAIRED_MISMATCH" for pair in pairs) == 1
    paired = next(pair for pair in pairs if pair["type"] == "PAIRED_MISMATCH")
    assert paired["mismatch_fields"] == ["retail_price"]


def test_daily_workbook_and_db_persistence(tmp_path: Path) -> None:
    source_inputs = inputs(tmp_path)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "csv_inputs": source_inputs,
        "outputPath": str(tmp_path / "reports" / "analysis.xlsx"),
        "priceTypeRules": [{"rule": "dealNumber != 0", "priceType": "PROMO"}],
    }), encoding="utf-8")
    db = tmp_path / "analysis.db"
    initialize_database(db)

    result = run(config, db, None)

    workbook = load_workbook(result["outputs"][0])
    assert workbook.sheetnames == ["Summary", "CDCS_missing_in_CPP",
                                   "CDCS_missing_in_CPP_analysis", "CPP_missing_in_CDCS", "CPP_missing_in_CDCS_analysis"]
    assert result["persistence"]["rows"] == 3
    connection = sqlite3.connect(str(db))
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM mismatch_input").fetchone()[0] == 3
        assert connection.execute(
            "SELECT store FROM mismatch_input ORDER BY row_id LIMIT 1").fetchone()[0] == "0035"
        assert connection.execute(
            "SELECT offering_number FROM mismatch_input ORDER BY row_id LIMIT 1").fetchone()[0] == "0000001"
    finally:
        connection.close()
