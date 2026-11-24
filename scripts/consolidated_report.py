"""Create a management workbook from explicitly named Project1 report files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from openpyxl import Workbook, load_workbook


def numeric(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def consolidate(files: list[Path], output: Path, since: Optional[str] = None, until: Optional[str] = None) -> dict:
    if not files:
        raise ValueError("At least one explicit workbook is required")
    rows = []
    for path in files:
        if not path.exists():
            raise FileNotFoundError(path)
        workbook = load_workbook(path, data_only=True, read_only=True)
        if "Summary" not in workbook.sheetnames or "All_Results" not in workbook.sheetnames:
            raise ValueError(
                f"{path.name}: required sheets Summary and All_Results are missing")
        summary = {}
        for metric, category, count in workbook["Summary"].iter_rows(min_row=2, values_only=True):
            summary[(str(metric), str(category))] = numeric(count)
        all_results = workbook["All_Results"]
        day_values = [str(row[1]) for row in all_results.iter_rows(
            min_row=2, values_only=True) if row and row[1]]
        day = min(day_values) if day_values else ""
        if since and day and day < since:
            continue
        if until and day and day > until:
            continue
        rows.append({"file": str(path.resolve()), "day": day, "total": summary.get(("total_results", "all"), 0),
                     "paired": summary.get(("paired_logical_groups", "all"), 0), "summary": {f"{key[0]}|{key[1]}": value for key, value in summary.items()}})
    workbook = Workbook()
    overview = workbook.active
    overview.title = "Overview"
    overview.append(["report_count", len(rows)])
    daily = workbook.create_sheet("Daily Summary")
    daily.append(["day", "file", "total_results", "paired_logical_groups"])
    issues = workbook.create_sheet("Issues to Review")
    issues.append(["day", "classification_or_kd", "count"])
    for row in rows:
        daily.append([row["day"], Path(row["file"]).name,
                     row["total"], row["paired"]])
        for metric, count in row["summary"].items():
            if metric.startswith("classification_count|"):
                issues.append([row["day"], metric.split("|", 1)[1], count])
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)
    return {"output": str(output), "reports": len(rows), "since": since, "until": until}


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--since")
    parser.add_argument("--until")
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    try:
        print(json.dumps(consolidate(args.report,
              args.output.resolve(), args.since, args.until), indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
