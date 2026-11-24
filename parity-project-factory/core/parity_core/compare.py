"""Stage 6-7 (Mode A): compare filtered source vs target and persist results.

config/comparison.json:
{
  "source": "<source dataset>", "target": "<target dataset>",
  "keys":   [{"name": "store", "source": "STORE", "target": "store_no", "type": "string", "zero_pad": 4}],
  "fields": [{"name": "retail_price", "source": "RTL", "target": "retail", "type": "decimal", "tolerance": 0.001}],
  "options": {"trim": true, "case_sensitive": true}
}
Records are paired on the normalised key. Results: MISMATCH (one row per
record, listing every differing field), MISSING_IN_TARGET, MISSING_IN_SOURCE,
DUPLICATE_KEY_SOURCE / DUPLICATE_KEY_TARGET. Matches are counted, not stored.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .config import ProjectContext
from .db import q
from .normalize import normalize, values_equal
from .results import ResultWriter


def _build_norm_table(ctx: ProjectContext, side: str, dataset_name: str, keys: list, fields: list, options: dict) -> int:
    db = ctx.db
    ds = ctx.dataset(dataset_name)
    if not db.table_exists(ds.filtered_table):
        raise RuntimeError(
            f"{ds.filtered_table} does not exist. Run the 'filter' stage first.")
    table = f"_norm_{side}"
    db.execute(f"DROP TABLE IF EXISTS {q(table)}")
    db.execute(
        f"CREATE TABLE {q(table)} (_ref INTEGER, _key TEXT, _vals TEXT, _rec TEXT)")
    cols = ds.columns
    select_cols = ", ".join([q("_rid")] + [q(c) for c in cols])
    buffer: List[list] = []
    total = 0
    for row in db.iter_query(f"SELECT {select_cols} FROM {q(ds.filtered_table)} ORDER BY {q('_rid')}", batch_size=ctx.batch_size):
        key_vals = [normalize(row.get(k.get(side, k["name"])),
                              k, side, options) for k in keys]
        vals = {f["name"]: normalize(
            row.get(f.get(side, f["name"])), f, side, options) for f in fields}
        rec = {c: row.get(c) for c in cols}
        buffer.append([row["_rid"], json.dumps(key_vals),
                      json.dumps(vals), json.dumps(rec)])
        total += 1
        if len(buffer) >= ctx.batch_size:
            db.insert_rows(table, ["_ref", "_key", "_vals", "_rec"], buffer)
            buffer = []
    db.insert_rows(table, ["_ref", "_key", "_vals", "_rec"], buffer)
    db.execute(f"CREATE INDEX {q('ix' + table + '_key')} ON {q(table)} (_key)")
    first = f"_first_{side}"
    db.execute(f"DROP TABLE IF EXISTS {q(first)}")
    db.execute(
        f"CREATE TABLE {q(first)} AS SELECT * FROM {q(table)} WHERE _ref IN (SELECT MIN(_ref) FROM {q(table)} GROUP BY _key)"
    )
    db.execute(f"CREATE INDEX {q('ix' + first + '_key')} ON {q(first)} (_key)")
    db.commit()
    return total


def run_compare(ctx: ProjectContext) -> Dict[str, Any]:
    cfg = ctx.comparison or {}
    keys, fields, options = cfg.get("keys", []), cfg.get(
        "fields", []), cfg.get("options", {})
    key_names = [k["name"] for k in keys]
    db = ctx.db
    writer = ResultWriter(ctx, "A", {"source": cfg.get(
        "source"), "target": cfg.get("target")})
    try:
        source_rows = _build_norm_table(
            ctx, "source", cfg["source"], keys, fields, options)
        target_rows = _build_norm_table(
            ctx, "target", cfg["target"], keys, fields, options)

        def key_dict(raw_key: str) -> Dict[str, Any]:
            return dict(zip(key_names, json.loads(raw_key)))

        for side, result_type in (("source", "DUPLICATE_KEY_SOURCE"), ("target", "DUPLICATE_KEY_TARGET")):
            sql = (
                f"SELECT n._key, d.c, n._rec FROM (SELECT _key, COUNT(*) AS c, MIN(_ref) AS r FROM {q('_norm_' + side)} "
                f"GROUP BY _key HAVING COUNT(*) > 1) d JOIN {q('_norm_' + side)} n ON n._ref = d.r"
            )
            for row in db.iter_query(sql, batch_size=ctx.batch_size):
                rec = json.loads(row["_rec"])
                writer.add(
                    result_type,
                    key_dict(row["_key"]),
                    source=rec if side == "source" else None,
                    target=rec if side == "target" else None,
                    details={"occurrences": row["c"]},
                )

        for this, other, result_type in (("source", "target", "MISSING_IN_TARGET"), ("target", "source", "MISSING_IN_SOURCE")):
            sql = (
                f"SELECT a._key, a._rec FROM {q('_first_' + this)} a WHERE NOT EXISTS "
                f"(SELECT 1 FROM {q('_first_' + other)} b WHERE b._key = a._key) ORDER BY a._ref"
            )
            for row in db.iter_query(sql, batch_size=ctx.batch_size):
                rec = json.loads(row["_rec"])
                writer.add(
                    result_type,
                    key_dict(row["_key"]),
                    source=rec if this == "source" else None,
                    target=rec if this == "target" else None,
                )

        matched = equal = 0
        field_counts = {f["name"]: 0 for f in fields}
        sql = (
            "SELECT s._key AS k, s._vals AS sv, s._rec AS sr, t._vals AS tv, t._rec AS tr "
            "FROM _first_source s JOIN _first_target t ON s._key = t._key ORDER BY s._ref"
        )
        for row in db.iter_query(sql, batch_size=ctx.batch_size):
            matched += 1
            sv, tv = json.loads(row["sv"]), json.loads(row["tv"])
            diffs = {}
            for f in fields:
                name = f["name"]
                if not values_equal(sv.get(name), tv.get(name), f):
                    diffs[name] = {"source": sv.get(
                        name), "target": tv.get(name)}
                    field_counts[name] += 1
            if not diffs:
                equal += 1
                continue
            writer.add(
                "MISMATCH",
                key_dict(row["k"]),
                source=json.loads(row["sr"]),
                target=json.loads(row["tr"]),
                mismatch_fields=list(diffs.keys()),
                details=diffs,
            )

        stats = {
            "source_dataset": cfg["source"],
            "target_dataset": cfg["target"],
            "source_rows": source_rows,
            "target_rows": target_rows,
            "source_unique_keys": db.count("_first_source"),
            "target_unique_keys": db.count("_first_target"),
            "matched_keys": matched,
            "matched_equal": equal,
            "matched_with_differences": matched - equal,
            "field_mismatch_counts": field_counts,
        }
        writer.finish(stats)
        from .report import export_mismatch_report

        stats["run_id"] = writer.run_id
        stats["results_by_type"] = writer.counts
        stats["mismatch_report"] = str(
            export_mismatch_report(ctx, writer.run_id))
        return stats
    except Exception as exc:
        writer.fail(str(exc))
        raise
