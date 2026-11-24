"""Inspect a sample input file and propose a dataset mapping for the spec.

Usage:
  python factory/inspect_sample.py --file sample.csv [--delimiter ","] [--encoding utf-8-sig] [--lines 20]
  python factory/inspect_sample.py --file sample.txt --fixed-width

Prints detected delimiter, headers, sample rows, inferred types and a draft
`columns` block. The draft must be confirmed with the user before use.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]
NAME_RE = re.compile(r"[^A-Za-z0-9_]+")


def snake(name: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name.strip())
    text = NAME_RE.sub("_", text).strip("_").lower() or "col"
    return f"c_{text}" if text[0].isdigit() else text


def infer_type(values: List[str]) -> dict:
    values = [v.strip() for v in values if v is not None and v.strip() not in ("", "NULL", "null")]
    if not values:
        return {"type": "string"}
    if all(re.fullmatch(r"-?\d+", v) for v in values):
        lead_zero = any(len(v) > 1 and v.startswith("0") for v in values)
        return {"type": "string", "note": "leading zeros present - keep as string"} if lead_zero else {"type": "integer"}
    if all(re.fullmatch(r"-?\d+(\.\d+)?", v.replace(",", "")) for v in values):
        return {"type": "decimal"}
    for fmt in DATE_FORMATS:
        try:
            for v in values:
                datetime.strptime(v, fmt)
            return {"type": "date" if "%H" not in fmt else "datetime", "format": fmt}
        except ValueError:
            continue
    return {"type": "string"}


def sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;|\t").delimiter
    except csv.Error:
        return ","


def inspect_delimited(path: Path, delimiter: Optional[str], encoding: str, lines: int) -> dict:
    with open(path, "r", encoding=encoding, newline="") as handle:
        head = "".join(handle.readline() for _ in range(lines + 1))
    delimiter = delimiter or sniff_delimiter(head)
    reader = csv.reader(head.splitlines(), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return {"error": "file is empty"}
    headers, data = rows[0], rows[1:]
    columns = []
    for i, header in enumerate(headers):
        values = [r[i] for r in data if i < len(r)]
        inferred = infer_type(values)
        column = {"name": snake(header), "source": header.strip(), "type": inferred["type"]}
        if "format" in inferred:
            column["format_hint"] = inferred["format"]
        if "note" in inferred:
            column["note"] = inferred["note"]
        columns.append(column)
    return {
        "file": str(path),
        "size_bytes": path.stat().st_size,
        "format": {"type": "csv", "delimiter": delimiter, "header": True, "encoding": encoding},
        "headers": headers,
        "sample_rows": data[: min(5, len(data))],
        "draft_columns": columns,
        "next_step": "Confirm names, types and which columns are needed with the user; add format_hint values as source_format/target_format in comparison keys/fields.",
    }


def inspect_fixed(path: Path, encoding: str, lines: int) -> dict:
    with open(path, "r", encoding=encoding) as handle:
        sample = [handle.readline().rstrip("\r\n") for _ in range(lines)]
    sample = [s for s in sample if s]
    width = max((len(s) for s in sample), default=0)
    blank = [all(i >= len(s) or s[i] == " " for s in sample) for i in range(width)]
    fields, start = [], None
    for i in range(width + 1):
        is_blank = i == width or blank[i]
        if not is_blank and start is None:
            start = i
        if is_blank and start is not None:
            fields.append((start + 1, i))
            start = None
    columns = [
        {"name": f"field_{n}", "start": s, "end": e, "type": infer_type([line[s - 1 : e] for line in sample])["type"]}
        for n, (s, e) in enumerate(fields, start=1)
    ]
    return {
        "file": str(path),
        "format": {"type": "fixed_width", "encoding": encoding},
        "line_length": width,
        "sample_lines": sample[:5],
        "draft_columns": columns,
        "next_step": "Column boundaries are guessed from blank positions. Ask the user for the official record layout and rename fields.",
    }


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", required=True)
    parser.add_argument("--delimiter", default=None)
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument("--lines", type=int, default=20)
    parser.add_argument("--fixed-width", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.file)
    if not path.is_file():
        print(f"ERROR: file not found: {path}")
        return 2
    result = inspect_fixed(path, args.encoding, args.lines) if args.fixed_width else inspect_delimited(path, args.delimiter, args.encoding, args.lines)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
