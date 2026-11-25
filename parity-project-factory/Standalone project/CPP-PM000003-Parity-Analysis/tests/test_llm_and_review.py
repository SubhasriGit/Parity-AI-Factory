# pyright: reportMissingImports=false
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import load_workbook

from init_database import initialize_database
from llm_bridge import export_candidates, import_findings
from review_and_report import write_workbook, import_review
import sqlite3


def seed(db: Path) -> int:
    initialize_database(db)
    connection = sqlite3.connect(str(db))
    cursor = connection.execute(
        "INSERT INTO mismatch_input(day,direction,store,offering_number,deal_number,price_type,effective_date,dealer_cost_price,retail_price,casting_price,timestamp_utc,message_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ["2026-08-14", "CDCS_missing_in_CPP", "0035", "0000001", "0001", "PROMO",
            "2026-08-14", "0.500", "1.000", "0.000", "2026-08-14 10:00:00", "m1"],
    )
    row_id = cursor.lastrowid
    connection.execute(
        "INSERT INTO mismatch_verdict VALUES (?,?,?,?,?,?,?)",
        [row_id, "POTENTIAL_ISSUE", "KD-2?", 0.45, "candidate",
            json.dumps({"rule": True}), json.dumps(["priceChangeEvent"])],
    )
    connection.commit()
    connection.close()
    return row_id


def test_llm_insufficient_is_noop_and_supported_finding_updates(tmp_path: Path) -> None:
    db = tmp_path / "analysis.db"
    row_id = seed(db)
    candidates = tmp_path / "candidates.json"
    assert export_candidates(db, candidates)["candidates"] == 1

    insufficient = tmp_path / "insufficient.json"
    insufficient.write_text(json.dumps({"findings": [
                            {"row_id": row_id, "classification": "INSUFFICIENT_EVIDENCE"}]}), encoding="utf-8")
    insufficient_result = import_findings(db, insufficient)
    assert insufficient_result["insufficient_evidence"] == 1
    assert insufficient_result["human_approval_required"] == 1
    connection = sqlite3.connect(str(db))
    support, missing = connection.execute(
        "SELECT supporting_evidence,missing_evidence FROM mismatch_verdict").fetchone()
    assert connection.execute("SELECT kd_code FROM mismatch_verdict").fetchone()[
        0] == "KD-2?"
    assert json.loads(support)["llm_review"]["requires_human_approval"] is True
    assert "human approval after LLM insufficient evidence" in json.loads(
        missing)
    connection.close()
    final_path = tmp_path / "non-blocked-final.xlsx"
    assert write_workbook(db, final_path, final_review=True)[
        "final_review"] is True
    final_workbook = load_workbook(final_path, read_only=True, data_only=True)
    final_headers = [cell.value for cell in final_workbook["All_Results"][1]]
    final_row = list(final_workbook["All_Results"].iter_rows(
        min_row=2, max_row=2, values_only=True))[0]
    assert final_row[final_headers.index(
        "confirmation_status")] == "HUMAN_APPROVAL_REQUIRED"

    findings = tmp_path / "findings.json"
    findings.write_text(json.dumps({"findings": [{"row_id": row_id, "classification": "IMS_DATA_ISSUE", "kd_code": "KD-7", "confidence": 0.8,
                        "hypothesis": "supported", "supporting_evidence": {"duplicate_dates": ["2026-08-13", "2026-08-14"]}, "missing_evidence": []}]}), encoding="utf-8")
    assert import_findings(db, findings)["updated"] == 1
    connection = sqlite3.connect(str(db))
    assert connection.execute("SELECT classification,kd_code FROM mismatch_verdict").fetchone(
    ) == ("IMS_DATA_ISSUE", "KD-7")
    support, missing = connection.execute(
        "SELECT supporting_evidence,missing_evidence FROM mismatch_verdict").fetchone()
    assert json.loads(support)[
        "llm_review"]["requires_human_approval"] is False
    assert "human approval after LLM insufficient evidence" not in json.loads(
        missing)
    connection.close()


def test_human_review_generates_final_directional_workbook(tmp_path: Path) -> None:
    db = tmp_path / "analysis.db"
    row_id = seed(db)
    insufficient = tmp_path / "insufficient.json"
    insufficient.write_text(json.dumps({"findings": [
        {"row_id": row_id, "classification": "INSUFFICIENT_EVIDENCE"}
    ]}), encoding="utf-8")
    assert import_findings(db, insufficient)["human_approval_required"] == 1
    review = tmp_path / "review.xlsx"
    write_workbook(db, review)
    workbook = load_workbook(review)
    sheet = workbook["All_Results"]
    headers = [cell.value for cell in sheet[1]]
    sheet.cell(2, headers.index("reviewed_classification") + 1, "EXPECTED")
    sheet.cell(2, headers.index("reviewed_kd_code") + 1, "KD-4")
    sheet.cell(2, headers.index("review_notes") + 1, "Confirmed by reviewer")
    sheet.cell(2, headers.index("reviewed_by") + 1, "CPP reviewer")
    sheet.cell(2, headers.index("reviewed_at") + 1, "2026-11-25T00:00:00Z")
    workbook.save(review)

    result = import_review(db, review)
    final_path = tmp_path / "final.xlsx"
    report = write_workbook(db, final_path, final_review=True)
    final = load_workbook(final_path)

    assert result["reviewed"] == 1 and result["disagreements"] == 1
    assert report["final_review"] is True
    assert final.sheetnames[:6] == [
        "Summary", "Classification_Summary", "Summary_detail", "All_Results", "CDCS_missing_in_CPP", "CPP_missing_in_CDCS"]
    assert [cell.value for cell in final["Classification_Summary"][1]] == [
        "classification", "kd_code", "count", "percent_of_total"]
    assert final["All_Results"].cell(2, 12).value == "EXPECTED"
    final_headers = [cell.value for cell in final["All_Results"][1]]
    assert final["All_Results"].cell(2, final_headers.index(
        "reviewed_classification") + 1).value == "EXPECTED"
    assert final["All_Results"].cell(2, final_headers.index(
        "review_notes") + 1).value == "Confirmed by reviewer"
