"""Stages 4-5: filter raw data into flt_<dataset> tables.

config/filters.json:
{
  "datasets": {
    "<dataset>": {
      "scope": "latest_load" | "all",
      "include": [ {"name": "...", "reason": "...", "condition": {...}} ],
      "exclude": [ {"name": "...", "reason": "...", "condition": {...}} ]
    }
  }
}
Datasets without an entry are copied unfiltered. Default scope is
`latest_load` for source/target/diff datasets and `all` for reference data.
"""

from __future__ import annotations

from typing import List, Optional

from .conditions import to_sql
from .config import Dataset, ProjectContext
from .db import q


def _scope_clause(ctx: ProjectContext, dataset: Dataset, scope: str) -> tuple:
    if scope == "all":
        return "1=1", []
    batch = ctx.db.scalar(
        "SELECT MAX(load_batch) FROM _loads WHERE dataset = ? AND status = 'OK'", [dataset.name]
    )
    if batch is None:
        return "1=0", []
    load_ids = [r[0] for r in ctx.db.query(
        "SELECT load_id FROM _loads WHERE dataset = ? AND load_batch = ? AND status = 'OK'", [dataset.name, batch]
    )]
    if dataset.load_policy.get("mode", "replace") == "replace":
        return "1=1", []
    marks = ", ".join("?" for _ in load_ids)
    return f"{q('_load_id')} IN ({marks})", load_ids


def filter_dataset(ctx: ProjectContext, dataset: Dataset) -> dict:
    db = ctx.db
    if not db.table_exists(dataset.raw_table):
        raise RuntimeError(f"Raw table {dataset.raw_table} does not exist. Run the 'load' stage first.")
    cfg = (ctx.filters.get("datasets") or {}).get(dataset.name, {})
    default_scope = "all" if dataset.role == "reference" else "latest_load"
    scope = cfg.get("scope", default_scope)
    scope_sql, scope_params = _scope_clause(ctx, dataset, scope)

    where = [f"({scope_sql})"]
    params: list = list(scope_params)
    rule_stats = []

    for rule in cfg.get("include", []) or []:
        sql, p = to_sql(rule.get("condition", rule), db)
        where.append(f"({sql})")
        params.extend(p)
    for rule in cfg.get("exclude", []) or []:
        sql, p = to_sql(rule.get("condition", rule), db)
        where.append(f"NOT COALESCE(({sql}), FALSE)")
        params.extend(p)
        hits = db.scalar(
            f"SELECT COUNT(*) FROM {q(dataset.raw_table)} WHERE ({scope_sql}) AND ({sql})",
            list(scope_params) + list(p),
        )
        rule_stats.append({"rule": rule.get("name", sql), "reason": rule.get("reason", ""), "rows_matched": int(hits or 0)})

    rows_in_scope = db.count(dataset.raw_table, scope_sql, scope_params)
    flt = dataset.filtered_table
    db.execute(f"DROP TABLE IF EXISTS {q(flt)}")
    db.execute(f"CREATE TABLE {q(flt)} AS SELECT * FROM {q(dataset.raw_table)} WHERE 1=0")
    db.execute(
        f"INSERT INTO {q(flt)} SELECT * FROM {q(dataset.raw_table)} WHERE {' AND '.join(where)}",
        params,
    )
    db.execute(f"CREATE INDEX IF NOT EXISTS {q('ix_' + flt + '_rid')} ON {q(flt)} ({q('_rid')})")
    db.commit()
    rows_out = db.count(flt)
    stats = {
        "dataset": dataset.name,
        "scope": scope,
        "rows_in_scope": rows_in_scope,
        "rows_kept": rows_out,
        "rows_removed": rows_in_scope - rows_out,
        "exclude_rules": rule_stats,
    }
    db.set_meta(f"{dataset.name}.filter_stats", stats)
    db.commit()
    return stats


def filter_all(ctx: ProjectContext, names: Optional[List[str]] = None) -> List[dict]:
    targets = [ctx.dataset(n) for n in names] if names else list(ctx.datasets.values())
    return [filter_dataset(ctx, ds) for ds in targets]
