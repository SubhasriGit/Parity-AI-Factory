"""Create or idempotently verify the canonical PM000003 SQLite database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "001_create_core_schema.sql"
SCHEMA_VERSION = 1
DEFAULT_DB = ROOT / "pm000003_mismatch_analysis.db"


def initialize_database(db_path: Path) -> dict:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    existed = db_path.exists()
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        current_version = int(connection.execute(
            "PRAGMA user_version").fetchone()[0])
        if current_version and current_version != SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {current_version} is incompatible with required version {SCHEMA_VERSION}."
            )
        connection.executescript(schema_sql)
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) VALUES (?, ?)",
            ["schema.version", str(SCHEMA_VERSION)],
        )
        connection.commit()
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        indexes = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        return {
            "database": str(db_path),
            "created": not existed,
            "schema_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
            "table_count": len(tables),
            "tables": tables,
            "index_count": len(indexes),
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="SQLite database path")
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    try:
        print(json.dumps(initialize_database(args.db.resolve()), indent=2))
        return 0
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
