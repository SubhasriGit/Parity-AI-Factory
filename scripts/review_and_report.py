"""Import human review and generate final PM000003 Excel outputs."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook, Workbook
from openpyxl.styles import PatternFill

VALID = {"EXPECTED", "IMS_DATA_ISSUE", "POTENTIAL_ISSUE"}
REVIEW_COLUMNS = ("reviewed_classification",
                  "reviewed_kd_code", "review_notes")


def load_rows(connection: sqlite3.Connection) -> list[dict]:
    cursor = connection.execute(
        "SELECT m.row_id,m.day,m.direction,m.store,m.offering_number,m.deal_number,m.price_type,m.effective_date,"
        "m.dealer_cost_price,m.retail_price,m.casting_price,v.classification,v.kd_code,v.confidence,v.hypothesis,"
        "v.supporting_evidence,v.missing_evidence FROM mismatch_input m LEFT JOIN mismatch_verdict v USING(row_id) ORDER BY m.row_id"
    )
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def import_review(db_path: Path, workbook_path: Path) -> dict:
    workbook = load_workbook(workbook_path, data_only=True)
    if "All_Results" not in workbook.sheetnames:
        raise ValueError("Review workbook must contain an All_Results sheet")
    sheet = workbook["All_Results"]
    headers = [cell.value for cell in sheet[1]]
    missing = [column for column in (
        "row_id", *REVIEW_COLUMNS) if column not in headers]
    if missing:
        raise ValueError(f"All_Results is missing review columns: {missing}")
    indexes = {name: index for index, name in enumerate(headers)}
    connection = sqlite3.connect(str(db_path))
    reviewed = disagreements = rejected = 0
    feedback = []
    try:
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row[indexes["reviewed_classification"]]:
                continue
            row_id = int(row[indexes["row_id"]])
            classification = str(
                row[indexes["reviewed_classification"]]).strip()
            if classification not in VALID:
                rejected += 1
                feedback.append(
                    {"row_id": row_id, "problem": f"invalid classification {classification}"})
                continue
            current = connection.execute(
                "SELECT classification,kd_code,hypothesis FROM mismatch_verdict WHERE row_id=?", [row_id]).fetchone()
            if current is None:
                rejected += 1
                continue
            kd = row[indexes["reviewed_kd_code"]]
            kd = str(kd).strip() if kd not in (None, "") else None
            notes = str(row[indexes["review_notes"]] or "")
            connection.execute(
                "UPDATE mismatch_verdict SET classification=?,kd_code=?,confidence=1.0,hypothesis=?,supporting_evidence=?,missing_evidence='[]' WHERE row_id=?",
                [classification, kd, notes or current[2], json.dumps(
                    {"manual_review": True, "source_workbook": workbook_path.name}), row_id],
            )
            reviewed += 1
            if (current[0], current[1]) != (classification, kd):
                disagreements += 1
                feedback.append({"row_id": row_id, "automated": {"classification": current[0], "kd_code": current[1]},
                                 "manual": {"classification": classification, "kd_code": kd}, "notes": notes})
        feedback_path = db_path.parent / "output" / "feedback" / "review_feedback.json"
        feedback_path.parent.mkdir(parents=True, exist_ok=True)
        feedback_path.write_text(json.dumps(
            {"reviewed": reviewed, "disagreements": disagreements, "items": feedback}, indent=2), encoding="utf-8")
        connection.commit()
        return {"reviewed": reviewed, "disagreements": disagreements, "rejected": rejected, "feedback": str(feedback_path)}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def write_workbook(db_path: Path, output: Path, final_review: bool = False) -> dict:
    connection = sqlite3.connect(str(db_path))
    try:
        rows = load_rows(connection)
    finally:
        connection.close()
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    summary.append(["metric", "category", "count"])
    summary.append(["total_results", "all", len(rows)])
    directions = sorted({row["direction"] for row in rows})
    for direction in directions:
        summary.append(["direction_count", direction, sum(
            row["direction"] == direction for row in rows)])
    for classification in sorted({row["classification"] or "UNCLASSIFIED" for row in rows}):
        summary.append(["classification_count", classification, sum(
            (row["classification"] or "UNCLASSIFIED") == classification for row in rows)])
    logical = {}
    for row in rows:
        key = (row["store"], row["offering_number"],
               row["deal_number"], row["price_type"], row["effective_date"])
        logical.setdefault(key, {"CDCS_missing_in_CPP": 0, "CPP_missing_in_CDCS": 0})[
            row["direction"]] += 1
    paired_groups = sum(min(counts["CDCS_missing_in_CPP"],
                            counts["CPP_missing_in_CDCS"]) for counts in logical.values())
    summary.append(["paired_logical_groups", "all", paired_groups])
    classification_counts = {}
    for row in rows:
        key = (row["classification"] or "UNCLASSIFIED", row["kd_code"] or "-")
        classification_counts[key] = classification_counts.get(key, 0) + 1
    classification_summary = workbook.create_sheet("Classification_Summary")
    classification_summary.append(
        ["classification", "kd_code", "count", "percent_of_total"])
    for (classification, kd_code), count in sorted(classification_counts.items(), key=lambda item: (-item[1], item[0])):
        percentage = round((count / len(rows)) * 100, 2) if rows else 0
        classification_summary.append(
            [classification, kd_code, count, percentage])
    summary_detail = workbook.create_sheet("Summary_detail")
    summary_detail.append(
        ["store", "price_type", "classification", "kd_code", "count"])
    detail_counts = {}
    for row in rows:
        key = (row["store"], row["price_type"], row["classification"]
               or "UNCLASSIFIED", row["kd_code"] or "-")
        detail_counts[key] = detail_counts.get(key, 0) + 1
    for key, count in sorted(detail_counts.items()):
        summary_detail.append([*key, count])

    headers = ["row_id", "day", "direction", "store", "offering_number", "deal_number", "price_type", "effective_date",
               "dealer_cost_price", "retail_price", "casting_price", "classification", "kd_code", "confidence", "hypothesis",
               "supporting_evidence", "missing_evidence", "confirmation_status", "confirmation_reason", *REVIEW_COLUMNS]
    fill = PatternFill(fill_type="solid", fgColor="D9D9D9")
    all_sheet = workbook.create_sheet("All_Results")
    all_sheet.append(headers)
    category_sheets = {}
    for direction in ("CDCS_missing_in_CPP", "CPP_missing_in_CDCS"):
        sheet = workbook.create_sheet(direction)
        sheet.append(headers)
        category_sheets[direction] = sheet
    for row in rows:
        reviewed_classification = reviewed_kd = review_notes = ""
        try:
            evidence = json.loads(row["supporting_evidence"] or "{}")
        except json.JSONDecodeError:
            evidence = {}
        try:
            missing_items = json.loads(row["missing_evidence"] or "[]")
        except json.JSONDecodeError:
            missing_items = []
        confirmation_status = "CONFIRMATION_REQUIRED" if missing_items else "CONFIRMED"
        confirmation_reason = "User review required. Confirm: " + \
            ", ".join(map(str, missing_items)
                      ) if missing_items else "Required rule evidence available in current analysis snapshot."
        if evidence.get("manual_review"):
            reviewed_classification = row["classification"]
            reviewed_kd = row["kd_code"] or ""
            review_notes = row["hypothesis"] or ""
        values = [row["row_id"], row["day"], row["direction"], row["store"], row["offering_number"], row["deal_number"], row["price_type"],
                  row["effective_date"], row["dealer_cost_price"], row["retail_price"], row["casting_price"], row["classification"], row["kd_code"],
                  row["confidence"], row["hypothesis"], row["supporting_evidence"], row["missing_evidence"], confirmation_status, confirmation_reason, reviewed_classification, reviewed_kd, review_notes]
        all_sheet.append(values)
        category_sheets.setdefault(row["direction"], all_sheet).append(values)
    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            cell.fill = fill
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)
    return {"output": str(output), "sheets": workbook.sheetnames, "rows": len(rows), "final_review": final_review}


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report")
    report.add_argument("--db", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--final", action="store_true")
    review = sub.add_parser("review-import")
    review.add_argument("--db", type=Path, required=True)
    review.add_argument("--file", type=Path, required=True)
    review.add_argument("--final-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "report":
            result = write_workbook(
                args.db.resolve(), args.output.resolve(), args.final)
        else:
            result = import_review(args.db.resolve(), args.file.resolve())
            if args.final_output:
                result["final_report"] = write_workbook(
                    args.db.resolve(), args.final_output.resolve(), True)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
