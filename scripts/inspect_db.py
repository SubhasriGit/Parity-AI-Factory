"""Read-only SQLite table, index, row-count, and metadata inspection."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional


def inspect(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        result = {"database": str(path), "schema_version": connection.execute(
            "PRAGMA user_version").fetchone()[0], "tables": {}}
        for table in tables:
            columns = [row[1] for row in connection.execute(
                f'PRAGMA table_info("{table}")')]
            result["tables"][table] = {"columns": columns, "rows": connection.execute(
                f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]}
        if "_metadata" in tables:
            result["metadata"] = dict(connection.execute(
                "SELECT key,value FROM _metadata ORDER BY key"))
        return result
    finally:
        connection.close()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inspect(args.db), indent=2))
        return 0
    except (OSError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
