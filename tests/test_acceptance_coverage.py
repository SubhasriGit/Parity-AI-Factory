# pyright: reportMissingImports=false
from __future__ import annotations

import sqlite3
from pathlib import Path

from openpyxl import load_workbook

from classify_kd import PREDICATE_ORDER
from consolidated_report import consolidate
from cpp_analyst import rebuild_cpp_data
from init_database import initialize_database
from review_and_report import write_workbook
from validate_database import validate_database
from inspect_cpp_csv import inspect


def test_classifier_contains_all_mandated_order_entries() -> None:
    expected = ["KD-7", "KD-4", "KD-3", "KD-1", "KD-5", "KD-9", "KD-6",
                "KD-10", "RAW_PARITY", "RAW_MISMATCH_SAME_DAY", "KD-2", "KD-8"]
    assert [name for name, _ in PREDICATE_ORDER] == expected


def test_truncated_packet_is_never_evidence(tmp_path: Path) -> None:
    db = tmp_path / "truncated.db"
    initialize_database(db)
    connection = sqlite3.connect(str(db))
    connection.execute("INSERT INTO cpp_price_packets(packetId,storeNumber,body,recCreationDateTime) VALUES (?,?,?,?)", [
                       1, "0035", "x" * 65535, "2026-08-14 10:00:00"])
    connection.commit()
    result = rebuild_cpp_data(connection)
    count = connection.execute("SELECT COUNT(*) FROM cpp_data").fetchone()[0]
    connection.close()
    assert result["inserted_rows"] == count == 0
    assert result["malformed_packets"][0]["reason"] == "suspected truncation"


def test_database_validator_detects_dropped_required_index(tmp_path: Path) -> None:
    db = tmp_path / "broken.db"
    initialize_database(db)
    connection = sqlite3.connect(str(db))
    connection.execute("DROP INDEX ix_mi_day")
    connection.commit()
    connection.close()
    result = validate_database(db)
    assert result["valid"] is False
    assert any("ix_mi_day" in problem for problem in result["problems"])


def test_csv_inspector_is_read_only(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    before = csv_path.read_bytes()
    result = inspect(csv_path)
    assert result["headers"] == ["a", "b"] and result["rows"] == 1
    assert csv_path.read_bytes() == before


def test_consolidation_does_not_mutate_sources(tmp_path: Path) -> None:
    db = tmp_path / "source.db"
    initialize_database(db)
    connection = sqlite3.connect(str(db))
    cursor = connection.execute("INSERT INTO mismatch_input(day,direction,store,offering_number,deal_number,price_type,effective_date,dealer_cost_price,retail_price,casting_price,timestamp_utc,message_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
                                "2026-08-14", "CDCS_missing_in_CPP", "0035", "0000001", "0001", "PROMO", "2026-08-14", "0.500", "1.000", "0.000", "2026-08-14 10:00:00", "m1"])
    connection.execute("INSERT INTO mismatch_verdict VALUES (?,?,?,?,?,?,?)", [
                       cursor.lastrowid, "POTENTIAL_ISSUE", "KD-2?", .4, "candidate", "{}", "[]"])
    connection.commit()
    connection.close()
    source = tmp_path / "source.xlsx"
    write_workbook(db, source, True)
    before = source.read_bytes()
    output = tmp_path / "consolidated.xlsx"
    consolidate([source], output)
    assert source.read_bytes() == before
    assert load_workbook(output, read_only=True).sheetnames == [
        "Overview", "Daily Summary", "Issues to Review"]
