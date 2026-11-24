"""Parity runs and result persistence shared by Mode A and Mode B."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import ProjectContext
from .db import Database
from .ingest import utc_now

RESULT_COLUMNS = [
    "run_id", "result_id", "result_type", "record_key", "key_json",
    "mismatch_fields", "source_json", "target_json", "details_json",
]


def new_run_id(db: Database) -> str:
    base = datetime.now().strftime("%Y%m%dT%H%M%S")
    run_id, suffix = base, 1
    while db.scalar("SELECT 1 FROM parity_run WHERE run_id = ?", [run_id]):
        suffix += 1
        run_id = f"{base}_{suffix}"
    return run_id


def latest_run_id(db: Database, completed_only: bool = True) -> Optional[str]:
    sql = "SELECT run_id FROM parity_run" + (" WHERE status = 'COMPLETED'" if completed_only else "")
    sql += " ORDER BY started_at DESC, run_id DESC LIMIT 1"
    return db.scalar(sql)


def resolve_run_id(ctx: ProjectContext, run_id: Optional[str]) -> str:
    if run_id:
        if not ctx.db.scalar("SELECT 1 FROM parity_run WHERE run_id = ?", [run_id]):
            raise RuntimeError(f"Run '{run_id}' not found. Use the 'status' command to list runs.")
        return run_id
    found = latest_run_id(ctx.db)
    if not found:
        raise RuntimeError("No completed parity run found. Run 'compare' (Mode A) or 'ingest-diff' (Mode B) first.")
    return found


class ResultWriter:
    def __init__(self, ctx: ProjectContext, mode: str, params: Dict[str, Any]):
        self.db = ctx.db
        self.batch_size = ctx.batch_size
        self.run_id = new_run_id(self.db)
        self.next_id = 1
        self.buffer: List[list] = []
        self.counts: Dict[str, int] = {}
        self.db.execute(
            "INSERT INTO parity_run (run_id, mode, started_at, status, params_json) VALUES (?,?,?,?,?)",
            [self.run_id, mode, utc_now(), "RUNNING", json.dumps(params, default=str)],
        )
        self.db.commit()

    def add(
        self,
        result_type: str,
        key: Dict[str, Any],
        source: Optional[Dict[str, Any]] = None,
        target: Optional[Dict[str, Any]] = None,
        mismatch_fields: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        result_id = self.next_id
        self.next_id += 1
        record_key = "|".join("" if v is None else str(v) for v in key.values())
        self.buffer.append(
            [
                self.run_id, result_id, result_type, record_key, json.dumps(key, default=str),
                ",".join(mismatch_fields or []),
                json.dumps(source, default=str) if source is not None else None,
                json.dumps(target, default=str) if target is not None else None,
                json.dumps(details, default=str) if details else None,
            ]
        )
        self.counts[result_type] = self.counts.get(result_type, 0) + 1
        if len(self.buffer) >= self.batch_size:
            self.flush()
        return result_id

    def flush(self) -> None:
        self.db.insert_rows("parity_result", RESULT_COLUMNS, self.buffer)
        self.buffer = []
        self.db.commit()

    def finish(self, stats: Dict[str, Any], status: str = "COMPLETED") -> None:
        self.flush()
        stats = dict(stats)
        stats["results_by_type"] = self.counts
        self.db.execute(
            "UPDATE parity_run SET finished_at = ?, status = ?, stats_json = ? WHERE run_id = ?",
            [utc_now(), status, json.dumps(stats, default=str), self.run_id],
        )
        self.db.commit()

    def fail(self, message: str) -> None:
        self.buffer = []
        self.db.rollback()
        self.db.execute("DELETE FROM parity_result WHERE run_id = ?", [self.run_id])
        self.db.execute(
            "UPDATE parity_run SET finished_at = ?, status = ?, stats_json = ? WHERE run_id = ?",
            [utc_now(), "FAILED", json.dumps({"error": message}), self.run_id],
        )
        self.db.commit()


def load_result_record(row: Dict[str, Any]) -> Dict[str, Any]:
    """Turn a parity_result row into the record shape used by rules and the LLM."""
    return {
        "run_id": row["run_id"],
        "result_id": row["result_id"],
        "result_type": row["result_type"],
        "record_key": row["record_key"],
        "key": json.loads(row["key_json"]) if row.get("key_json") else {},
        "mismatch_fields": [f for f in (row.get("mismatch_fields") or "").split(",") if f],
        "source": json.loads(row["source_json"]) if row.get("source_json") else None,
        "target": json.loads(row["target_json"]) if row.get("target_json") else None,
        "details": json.loads(row["details_json"]) if row.get("details_json") else {},
    }


def run_stats(db: Database, run_id: str) -> Dict[str, Any]:
    raw = db.scalar("SELECT stats_json FROM parity_run WHERE run_id = ?", [run_id])
    return json.loads(raw) if raw else {}
