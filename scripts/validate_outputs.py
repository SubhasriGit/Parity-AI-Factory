"""Read-only validation of PM000003 database and workbook reconciliation."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook

REQUIRED_FINAL_SHEETS = {"Summary", "Summary_detail",
                         "All_Results", "CDCS_missing_in_CPP", "CPP_missing_in_CDCS"}
REVIEW_COLUMNS = {"reviewed_classification",
                  "reviewed_kd_code", "review_notes"}


def validate(db_path: Path, workbook_path: Path) -> dict:
    problems = []
    if not db_path.exists():
        return {"valid": False, "problems": [f"database does not exist: {db_path}"]}
    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    try:
        mismatch_count = int(connection.execute(
            "SELECT COUNT(*) FROM mismatch_input").fetchone()[0])
        verdict_count = int(connection.execute(
            "SELECT COUNT(*) FROM mismatch_verdict").fetchone()[0])
        if mismatch_count != verdict_count:
            problems.append(
                f"mismatch/verdict count differs: {mismatch_count} != {verdict_count}")
    finally:
        connection.close()
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    missing_sheets = sorted(REQUIRED_FINAL_SHEETS - set(workbook.sheetnames))
    if missing_sheets:
        problems.append(f"missing sheets: {missing_sheets}")
    result_rows = 0
    if "All_Results" in workbook.sheetnames:
        sheet = workbook["All_Results"]
        headers = [cell.value for cell in next(
            sheet.iter_rows(min_row=1, max_row=1))]
        if REVIEW_COLUMNS - set(headers):
            problems.append(
                f"All_Results missing review columns: {sorted(REVIEW_COLUMNS - set(headers))}")
        result_rows = max(0, sheet.max_row - 1)
        if result_rows != mismatch_count:
            problems.append(
                f"workbook rows differ from DB mismatch rows: {result_rows} != {mismatch_count}")
    if "Summary" in workbook.sheetnames:
        summary = {(str(row[0]), str(row[1])): row[2]
                   for row in workbook["Summary"].iter_rows(min_row=2, values_only=True)}
        reported = summary.get(("total_results", "all"))
        if int(reported or 0) != mismatch_count:
            problems.append(
                f"Summary total differs from DB: {reported} != {mismatch_count}")
    return {"valid": not problems, "problems": problems, "mismatch_rows": mismatch_count,
            "verdict_rows": verdict_count, "workbook_rows": result_rows}


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    result = validate(args.db.resolve(), args.workbook.resolve())
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
