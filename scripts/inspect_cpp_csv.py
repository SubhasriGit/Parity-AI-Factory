"""Inspect a CPP CSV's headers, row count, and representative values without mutation."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Optional


def inspect(path: Path, samples: int = 3) -> dict:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        count = 0
        for row in reader:
            count += 1
            if len(rows) < samples:
                rows.append(row)
    return {"file": str(path), "headers": reader.fieldnames or [], "rows": count, "samples": rows}


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inspect(args.file, args.samples), indent=2))
        return 0
    except OSError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
