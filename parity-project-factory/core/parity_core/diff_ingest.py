"""Stage 6-7 (Mode B): turn a supplied difference report into parity results.

Use when another tool (e.g. New Relic, a vendor report) already produced the
differences and the project only needs analysis.

config/diff_ingest.json:
{
  "inputs": [
    {"dataset": "diff_src_only", "result_type": "MISSING_IN_TARGET"},
    {"dataset": "diff_tgt_only", "result_type": "MISSING_IN_SOURCE"}
    // or one dataset with a direction column:
    // {"dataset": "diffs", "direction_column": "direction",
    //  "direction_map": {"in legacy only": "MISSING_IN_TARGET", "in cloud only": "MISSING_IN_SOURCE",
    //                    "value mismatch": "MISMATCH"}}
  ],
  "keys": ["store", {"name": "offering", "column": "offeringNumber", "type": "string"}],
  "compare_fields": ["dealerCostPrice", "retailPrice"],
  "pair_opposite_directions": true
}
"MISSING_IN_TARGET" = present in source only; "MISSING_IN_SOURCE" = present in
target only. With pairing enabled, opposite-direction rows sharing the same
key become one MISMATCH (value difference) instead of two missing records.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List, Tuple

from .config import ProjectContext
from .db import q
from .normalize import normalize, values_equal
from .results import ResultWriter


def _key_specs(cfg: dict) -> List[dict]:
    specs = []
    for key in cfg.get("keys", []):
        if isinstance(key, str):
            specs.append({"name": key, "column": key, "type": "string"})
        else:
            spec = dict(key)
            spec.setdefault("column", spec["name"])
            specs.append(spec)
    return specs


def _field_specs(cfg: dict) -> List[dict]:
    specs = []
    for item in cfg.get("compare_fields", []):
        if isinstance(item, str):
            specs.append({"name": item, "column": item, "type": "string"})
        else:
            spec = dict(item)
            spec.setdefault("column", spec["name"])
            specs.append(spec)
    return specs


def run_ingest_diff(ctx: ProjectContext) -> Dict[str, Any]:
    cfg = ctx.diff_ingest or {}
    db = ctx.db
    key_specs, field_specs = _key_specs(cfg), _field_specs(cfg)
    options = cfg.get("options", {})
    pair = cfg.get("pair_opposite_directions", True)
    writer = ResultWriter(
        ctx, "B", {"inputs": [e.get("dataset") for e in cfg.get("inputs", [])]})
    try:
        groups: "OrderedDict[str, Dict[str, list]]" = OrderedDict()
        rows_read = 0
        unknown_direction: Dict[str, int] = {}
        for entry in cfg.get("inputs", []):
            ds = ctx.dataset(entry["dataset"])
            if not db.table_exists(ds.filtered_table):
                raise RuntimeError(
                    f"{ds.filtered_table} does not exist. Run the 'filter' stage first.")
            cols = ds.columns
            select_cols = ", ".join([q("_rid")] + [q(c) for c in cols])
            for row in db.iter_query(f"SELECT {select_cols} FROM {q(ds.filtered_table)} ORDER BY {q('_rid')}", batch_size=ctx.batch_size):
                rows_read += 1
                if entry.get("result_type"):
                    result_type = entry["result_type"]
                else:
                    direction = (
                        row.get(entry["direction_column"]) or "").strip()
                    result_type = entry.get("direction_map", {}).get(direction)
                    if result_type is None:
                        unknown_direction[direction] = unknown_direction.get(
                            direction, 0) + 1
                        continue
                key_vals = [
                    normalize(row.get(k["column"]), k, "source", options) for k in key_specs]
                record = {c: row.get(c) for c in cols}
                record["_dataset"] = ds.name
                key_str = "\x1f".join("" if v is None else v for v in key_vals)
                bucket = groups.setdefault(key_str, {"key": key_vals, "MISSING_IN_TARGET": [
                ], "MISSING_IN_SOURCE": [], "MISMATCH": []})
                bucket.setdefault(result_type, []).append(record)

        key_names = [k["name"] for k in key_specs]
        paired = 0
        field_counts = {f["name"]: 0 for f in field_specs}
        for bucket in groups.values():
            key = dict(zip(key_names, bucket["key"]))
            src_only, tgt_only = bucket["MISSING_IN_TARGET"], bucket["MISSING_IN_SOURCE"]
            if pair:
                while src_only and tgt_only:
                    s, t = src_only.pop(0), tgt_only.pop(0)
                    diffs = {}
                    for f in field_specs:
                        sv = normalize(
                            s.get(f["column"]), f, "source", options)
                        tv = normalize(
                            t.get(f["column"]), f, "target", options)
                        if not values_equal(sv, tv, f):
                            diffs[f["name"]] = {"source": sv, "target": tv}
                            field_counts[f["name"]] += 1
                    writer.add("MISMATCH", key, source=s, target=t, mismatch_fields=list(diffs), details=diffs or {
                               "note": "rows paired on key; compare_fields equal - difference is in non-compared columns"})
                    paired += 1
            for s in src_only:
                writer.add("MISSING_IN_TARGET", key, source=s)
            for t in tgt_only:
                writer.add("MISSING_IN_SOURCE", key, target=t)
            for m in bucket.get("MISMATCH", []):
                writer.add("MISMATCH", key, source=m, target=None, mismatch_fields=[
                ], details={"note": "mismatch row supplied by diff report"})
            for other_type, items in bucket.items():
                if other_type in ("key", "MISSING_IN_TARGET", "MISSING_IN_SOURCE", "MISMATCH"):
                    continue
                for item in items:
                    writer.add(other_type, key, source=item)

        stats = {
            "diff_rows_read": rows_read,
            "unique_keys": len(groups),
            "paired_into_mismatch": paired,
            "unknown_direction_values": unknown_direction,
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
