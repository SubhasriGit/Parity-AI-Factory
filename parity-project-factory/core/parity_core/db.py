"""Local analysis database wrapper (SQLite default, DuckDB optional)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Iterator, List, Optional, Sequence

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CORE_SCHEMA = [
    "CREATE TABLE IF NOT EXISTS _metadata (key TEXT PRIMARY KEY, value TEXT)",
    """CREATE TABLE IF NOT EXISTS _loads (
        load_id INTEGER PRIMARY KEY,
        load_batch INTEGER,
        dataset TEXT,
        source_file TEXT,
        file_sha256 TEXT,
        file_size INTEGER,
        rows_read INTEGER,
        rows_inserted INTEGER,
        rows_skipped INTEGER,
        policy TEXT,
        loaded_at TEXT,
        status TEXT,
        message TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS parity_run (
        run_id TEXT PRIMARY KEY,
        mode TEXT,
        started_at TEXT,
        finished_at TEXT,
        status TEXT,
        params_json TEXT,
        stats_json TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS parity_result (
        run_id TEXT,
        result_id INTEGER,
        result_type TEXT,
        record_key TEXT,
        key_json TEXT,
        mismatch_fields TEXT,
        source_json TEXT,
        target_json TEXT,
        details_json TEXT,
        PRIMARY KEY (run_id, result_id)
    )""",
    """CREATE TABLE IF NOT EXISTS verdict (
        run_id TEXT,
        result_id INTEGER,
        verdict_source TEXT,
        classification TEXT,
        kd_code TEXT,
        confidence DOUBLE,
        hypothesis TEXT,
        evidence_json TEXT,
        created_at TEXT,
        PRIMARY KEY (run_id, result_id, verdict_source)
    )""",
]

CORE_TABLES = ("_metadata", "_loads", "parity_run", "parity_result", "verdict")


def check_identifier(name: str, what: str = "identifier") -> str:
    if not isinstance(name, str) or not IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Invalid {what} '{name}': use letters, digits and underscores only, not starting with a digit."
        )
    return name


def q(name: str) -> str:
    """Quote an SQL identifier."""
    return '"' + str(name).replace('"', '""') + '"'


def named_to_positional(sql: str, params: dict) -> tuple:
    """Convert ':name' placeholders to '?' so queries work on both engines."""
    values: List[Any] = []

    def repl(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name not in params:
            raise KeyError(f"Missing SQL parameter ':{name}'")
        values.append(params[name])
        return "?"

    converted = re.sub(r"(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)", repl, sql)
    return converted, values


class Database:
    def __init__(self, engine: str, path: Path):
        self.engine = (engine or "sqlite").lower()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.engine == "sqlite":
            self.conn = sqlite3.connect(str(self.path))
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
        elif self.engine == "duckdb":
            try:
                import duckdb  # type: ignore
            except ImportError as exc:  # pragma: no cover - depends on env
                raise RuntimeError(
                    "database.engine is 'duckdb' but the duckdb package is not installed. "
                    "Run: pip install duckdb  (or switch database.engine to 'sqlite')."
                ) from exc
            self.conn = duckdb.connect(str(self.path))
        else:
            raise ValueError(f"Unsupported database engine '{engine}'. Use 'sqlite' or 'duckdb'.")

    # -- basic execution -------------------------------------------------
    def execute(self, sql: str, params: Optional[Sequence[Any]] = None):
        if params is None:
            return self.conn.execute(sql)
        return self.conn.execute(sql, list(params))

    def query(self, sql: str, params: Optional[Sequence[Any]] = None) -> list:
        return self.execute(sql, params).fetchall()

    def scalar(self, sql: str, params: Optional[Sequence[Any]] = None) -> Any:
        row = self.execute(sql, params).fetchone()
        return row[0] if row else None

    def iter_query(
        self, sql: str, params: Optional[Sequence[Any]] = None, batch_size: int = 10000
    ) -> Iterator[tuple]:
        """Stream rows on a separate cursor so writes can happen meanwhile."""
        cursor = self.conn.cursor()
        if params is None:
            cursor.execute(sql)
        else:
            cursor.execute(sql, list(params))
        columns = [d[0] for d in cursor.description]
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield dict(zip(columns, row))
        cursor.close()

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        rows = list(rows)
        if not rows:
            return
        self.conn.executemany(sql, rows)

    def insert_rows(self, table: str, columns: Sequence[str], rows: List[Sequence[Any]], ignore: bool = False) -> None:
        if not rows:
            return
        verb = "INSERT OR IGNORE" if ignore else "INSERT"
        cols = ", ".join(q(c) for c in columns)
        if self.engine == "duckdb":
            import pandas as pd

            frame = pd.DataFrame(rows, columns=list(columns), dtype=object)
            self.conn.register("_parity_tmp", frame)
            try:
                self.conn.execute(f"{verb} INTO {q(table)} ({cols}) SELECT {cols} FROM _parity_tmp")
            finally:
                self.conn.unregister("_parity_tmp")
            return
        marks = ", ".join("?" for _ in columns)
        self.conn.executemany(f"{verb} INTO {q(table)} ({cols}) VALUES ({marks})", rows)

    def commit(self) -> None:
        if self.engine == "sqlite":
            self.conn.commit()

    def rollback(self) -> None:
        if self.engine == "sqlite":
            self.conn.rollback()

    def close(self) -> None:
        try:
            self.commit()
        finally:
            self.conn.close()

    # -- introspection ---------------------------------------------------
    def table_exists(self, name: str) -> bool:
        if self.engine == "sqlite":
            sql = "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?"
        else:
            sql = "SELECT 1 FROM information_schema.tables WHERE table_name = ?"
        return self.execute(sql, [name]).fetchone() is not None

    def columns(self, table: str) -> List[str]:
        if self.engine == "sqlite":
            return [row[1] for row in self.query(f"PRAGMA table_info({q(table)})")]
        return [
            row[0]
            for row in self.query(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ? ORDER BY ordinal_position",
                [table],
            )
        ]

    def tables(self) -> List[str]:
        if self.engine == "sqlite":
            sql = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        else:
            sql = "SELECT table_name FROM information_schema.tables ORDER BY table_name"
        return [row[0] for row in self.query(sql)]

    def count(self, table: str, where: str = "", params: Optional[Sequence[Any]] = None) -> int:
        sql = f"SELECT COUNT(*) FROM {q(table)}" + (f" WHERE {where}" if where else "")
        return int(self.scalar(sql, params) or 0)

    def num(self, expr: str) -> str:
        """SQL expression casting text to a number (NULL when not numeric on DuckDB)."""
        if self.engine == "duckdb":
            return f"TRY_CAST({expr} AS DOUBLE)"
        return f"CAST({expr} AS REAL)"

    # -- core schema -----------------------------------------------------
    def init_core_schema(self) -> None:
        for statement in CORE_SCHEMA:
            self.execute(statement)
        self.commit()

    def set_meta(self, key: str, value: Any) -> None:
        self.execute("DELETE FROM _metadata WHERE key = ?", [key])
        self.execute("INSERT INTO _metadata (key, value) VALUES (?, ?)", [key, None if value is None else str(value)])

    def get_meta(self, key: str) -> Optional[str]:
        if not self.table_exists("_metadata"):
            return None
        return self.scalar("SELECT value FROM _metadata WHERE key = ?", [key])

    def next_id(self, table: str, column: str, where: str = "", params: Optional[Sequence[Any]] = None) -> int:
        sql = f"SELECT MAX({q(column)}) FROM {q(table)}" + (f" WHERE {where}" if where else "")
        current = self.scalar(sql, params)
        return int(current or 0) + 1
