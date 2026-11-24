"""Stage 10-11: user-facing reports and manual review feedback.

report        -> output/reports/<slug>_parity_<run_id>.xlsx (+ CSV of all results)
review-import -> reads reviewer columns from the workbook, stores them as
                 verdict_source = 'manual' and writes a feedback file used to
                 tune rules and prompts (see skill: tune-from-review).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .classify import all_verdicts, final_verdicts
from .config import ProjectContext
from .ingest import utc_now
from .results import load_result_record, resolve_run_id, run_stats

EXCEL_MAX_ROWS = 1_048_000
ILLEGAL = re.compile(r"[\000-\010]|[\013-\014]|[\016-\037]")
REVIEW_COLUMNS = ["reviewed_classification",
                  "reviewed_kd_code", "review_notes"]


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return ILLEGAL.sub("", value)
    return value


def _flatten(prefix: str, data: Optional[dict]) -> Dict[str, Any]:
    if not data:
        return {}
    return {f"{prefix}.{k}": v for k, v in data.items()}


def build_frames(ctx: ProjectContext, run_id: str) -> Dict[str, Any]:
    import pandas as pd

    best = final_verdicts(ctx, run_id)
    everything = all_verdicts(ctx, run_id)
    titles = {r.get("code"): r.get("title")
              for r in ctx.rules.get("rules", [])}
    rows: List[dict] = []
    diff_rows: List[dict] = []
    for raw in ctx.db.iter_query("SELECT * FROM parity_result WHERE run_id = ? ORDER BY result_id", [run_id], batch_size=ctx.batch_size):
        rec = load_result_record(raw)
        verdict = best.get(rec["result_id"], {})
        by_source = everything.get(rec["result_id"], {})
        row = {
            "run_id": run_id,
            "result_id": rec["result_id"],
            "result_type": rec["result_type"],
            **_flatten("key", rec["key"]),
            "mismatch_fields": ",".join(rec["mismatch_fields"]),
            "classification": verdict.get("classification", "UNCLASSIFIED"),
            "kd_code": verdict.get("kd_code"),
            "kd_title": titles.get(verdict.get("kd_code")),
            "confidence": verdict.get("confidence"),
            "hypothesis": verdict.get("hypothesis"),
            "verdict_source": verdict.get("verdict_source"),
            "rule_verdict": _short(by_source.get("rule")),
            "llm_verdict": _short(by_source.get("llm")),
        }
        row.update(_flatten("source", rec["source"]))
        row.update(_flatten("target", rec["target"]))
        manual = by_source.get("manual")
        row["reviewed_classification"] = manual["classification"] if manual else None
        row["reviewed_kd_code"] = manual["kd_code"] if manual else None
        row["review_notes"] = manual["hypothesis"] if manual else None
        rows.append(row)
        for field, values in (rec["details"] or {}).items():
            if isinstance(values, dict) and ("source" in values or "target" in values):
                diff_rows.append({
                    "result_id": rec["result_id"],
                    "record_key": rec["record_key"],
                    "field": field,
                    "source_value": values.get("source"),
                    "target_value": values.get("target"),
                    "classification": row["classification"],
                    "kd_code": row["kd_code"],
                })

    results = pd.DataFrame(rows)
    if not results.empty:
        fixed = [c for c in results.columns if not c.startswith(
            ("source.", "target.")) and c not in REVIEW_COLUMNS]
        side_cols = [c for c in results.columns if c.startswith(
            ("source.", "target."))]
        results = results[fixed + side_cols + REVIEW_COLUMNS]

    stats = run_stats(ctx.db, run_id)
    run_row = ctx.db.execute(
        "SELECT mode, started_at, finished_at, status FROM parity_run WHERE run_id = ?", [run_id]).fetchone()
    summary = [
        ("project", ctx.project.get("name")),
        ("run_id", run_id),
        ("mode", run_row[0] if run_row else ctx.mode),
        ("run_started_utc", run_row[1] if run_row else None),
        ("run_finished_utc", run_row[2] if run_row else None),
        ("report_generated_utc", utc_now()),
        ("total_results", len(rows)),
    ]
    for key, value in stats.items():
        summary.append((key, json.dumps(value) if isinstance(
            value, (dict, list)) else value))
    summary_df = pd.DataFrame(summary, columns=["metric", "value"])

    if results.empty:
        pivot = pd.DataFrame(
            columns=["classification", "kd_code", "kd_title", "result_type", "count"])
    else:
        pivot = (
            results.fillna({"kd_code": "-", "kd_title": "-"})
            .groupby(["classification", "kd_code", "kd_title", "result_type"], dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
    llm_classes = set(ctx.llm.get("classifications", ["POTENTIAL_ISSUE"]))
    potential = results[results["classification"].isin(
        llm_classes)] if not results.empty else results
    catalogue = pd.DataFrame([
        {k: r.get(k) for k in ("code", "title", "classification",
                               "priority", "description", "evidence_needed", "enabled")}
        for r in ctx.rules.get("rules", [])
    ])
    return {
        "Summary": summary_df,
        "Classification_summary": pivot,
        "Results": results,
        "Potential_issues": potential,
        "Field_diffs": pd.DataFrame(diff_rows),
        "KD_catalogue": catalogue,
    }


def _short(verdict: Optional[dict]) -> Optional[str]:
    if not verdict:
        return None
    return f"{verdict['classification']} [{verdict.get('kd_code') or '-'}] conf={verdict.get('confidence')}"


def export_mismatch_report(ctx: ProjectContext, run_id: str) -> Path:
    """Export the result table immediately after comparison or supplied-report ingestion."""
    frames = build_frames(ctx, run_id)
    out_dir = ctx.output_dir / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ctx.slug}_mismatch_report_{run_id}.csv"
    frames["Results"].to_csv(path, index=False, encoding="utf-8-sig")
    return path


def build_final_frames(ctx: ProjectContext, run_id: str) -> Dict[str, Any]:
    import pandas as pd

    frames = build_frames(ctx, run_id)
    results = frames["Results"].copy()
    if results.empty:
        result_types = pd.Series(dtype="object")
        classifications = pd.Series(dtype="object")
    else:
        result_types = results["result_type"].astype(str)
        classifications = results["classification"].astype(str)

    summary_rows = [
        {"metric": "project", "category": None,
            "count": None, "value": ctx.project.get("name")},
        {"metric": "run_id", "category": None, "count": None, "value": run_id},
        {"metric": "total_results", "category": "all",
            "count": len(results), "value": None},
        {"metric": "manual_reviewed", "category": "review", "count": int(
            (results["verdict_source"] == "manual").sum()) if not results.empty else 0, "value": None},
        {"metric": "not_manually_reviewed", "category": "review", "count": int(
            (results["verdict_source"] != "manual").sum()) if not results.empty else 0, "value": None},
    ]
    for result_type, count in result_types.value_counts().sort_index().items():
        summary_rows.append({"metric": "result_type_count",
                            "category": result_type, "count": int(count), "value": None})
    for classification, count in classifications.value_counts().sort_index().items():
        summary_rows.append({"metric": "classification_count",
                            "category": classification, "count": int(count), "value": None})

    def select(types: List[str]) -> Any:
        return results[results["result_type"].isin(types)].copy() if not results.empty else results.copy()

    return {
        "Summary": pd.DataFrame(summary_rows),
        "Mismatches": select(["MISMATCH"]),
        "Missing_In_Source": select(["MISSING_IN_SOURCE"]),
        "Missing_In_Target": select(["MISSING_IN_TARGET"]),
        "Duplicate_Keys": select(["DUPLICATE_KEY_SOURCE", "DUPLICATE_KEY_TARGET"]),
        "All_Results": results,
        "Field_diffs": frames["Field_diffs"],
        "Classification_Summary": frames["Classification_summary"],
        "KD_Catalogue": frames["KD_catalogue"],
    }


def run_report(ctx: ProjectContext, run_id: Optional[str] = None, final_review: bool = False) -> Dict[str, Any]:
    import pandas as pd

    run_id = resolve_run_id(ctx, run_id)
    frames = build_final_frames(
        ctx, run_id) if final_review else build_frames(ctx, run_id)
    out_dir = ctx.output_dir / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    formats = ctx.reports.get("formats", ["xlsx", "csv"])
    written = []
    notes = []
    base = f"{ctx.slug}_parity_{run_id}"
    if final_review:
        base = f"{ctx.slug}_final_review_{run_id}"
    if "csv" in formats and not final_review:
        path = out_dir / f"{base}_results.csv"
        frames["Results"].to_csv(path, index=False, encoding="utf-8-sig")
        written.append(str(path))
    if "xlsx" in formats:
        path = out_dir / f"{base}.xlsx"
        try:
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                for name, frame in frames.items():
                    if len(frame) > EXCEL_MAX_ROWS:
                        notes.append(
                            f"Sheet {name} truncated to {EXCEL_MAX_ROWS} rows (full data in CSV / DB)")
                        frame = frame.head(EXCEL_MAX_ROWS)
                    frame = frame.apply(lambda col: col.map(
                        _clean)) if not frame.empty else frame
                    frame.to_excel(writer, sheet_name=name, index=False)
                    sheet = writer.sheets[name]
                    sheet.freeze_panes = "A2"
                    for column_cells in sheet.columns:
                        width = min(60, max(
                            10, *(len(str(c.value)) if c.value is not None else 0 for c in column_cells[:200])))
                        sheet.column_dimensions[column_cells[0]
                                                .column_letter].width = width + 2
        except PermissionError:
            raise RuntimeError(
                f"Cannot write {path}: the file is probably open in Excel. Close it and rerun 'report'.")
        written.append(str(path))
    counts = frames.get("Classification_summary",
                        frames.get("Classification_Summary"))
    results = frames.get("Results", frames.get("All_Results"))
    return {
        "run_id": run_id,
        "final_review": final_review,
        "files": written,
        "notes": notes,
        "total_results": len(results) if results is not None else 0,
        "classification_summary": counts.to_dict(orient="records") if counts is not None and not counts.empty else [],
    }


def run_review_import(ctx: ProjectContext, workbook: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    import pandas as pd

    path = Path(workbook)
    if not path.is_absolute():
        path = (ctx.root / path) if (ctx.root /
                                     path).exists() else path.resolve()
    frame = pd.read_excel(path, sheet_name="Results", dtype=str)
    missing = [c for c in ["run_id", "result_id",
                           "reviewed_classification"] if c not in frame.columns]
    if missing:
        raise RuntimeError(
            f"{path.name}: Results sheet is missing column(s) {missing}")
    file_runs = sorted(set(frame["run_id"].dropna()))
    if run_id is None:
        if len(file_runs) != 1:
            raise RuntimeError(
                f"Workbook contains runs {file_runs}; pass --run-id")
        run_id = file_runs[0]
    run_id = resolve_run_id(ctx, run_id)
    allowed = set((ctx.rules.get("classifications") or {}).keys())
    codes = {r.get("code") for r in ctx.rules.get("rules", [])}
    previous = final_verdicts(ctx, run_id)

    reviewed = frame[frame["reviewed_classification"].fillna(
        "").str.strip() != ""]
    rows, problems, feedback = [], [], []
    agree = disagree = 0
    for _, item in reviewed.iterrows():
        try:
            result_id = int(float(item["result_id"]))
        except (TypeError, ValueError):
            problems.append(
                f"row with result_id '{item['result_id']}' is not numeric")
            continue
        classification = str(item["reviewed_classification"]).strip()
        if classification not in allowed:
            problems.append(
                f"result {result_id}: classification '{classification}' not in {sorted(allowed)}")
            continue
        kd = str(item.get("reviewed_kd_code") or "").strip() or None
        if kd in ("nan", "-"):
            kd = None
        if kd and kd not in codes:
            problems.append(
                f"result {result_id}: kd_code '{kd}' is not in rules/known_discrepancies.json (stored anyway - consider adding it)")
        notes = item.get("review_notes")
        notes = None if notes is None or str(notes) == "nan" else str(notes)
        rows.append([run_id, result_id, "manual", classification, kd, 1.0,
                    notes or "", json.dumps({"workbook": path.name}), utc_now()])
        prior = previous.get(result_id)
        if prior and prior["verdict_source"] == "manual":
            prior = None
        auto = (prior or {}).get(
            "classification"), (prior or {}).get("kd_code")
        if auto == (classification, kd):
            agree += 1
        else:
            disagree += 1
            feedback.append({
                "result_id": result_id,
                "result_type": item.get("result_type"),
                "record_key": "|".join(str(item[c]) for c in frame.columns if c.startswith("key.") and str(item[c]) != "nan"),
                "automated": {"source": (prior or {}).get("verdict_source"), "classification": auto[0], "kd_code": auto[1], "hypothesis": (prior or {}).get("hypothesis")},
                "reviewed": {"classification": classification, "kd_code": kd, "notes": notes},
            })
    if rows:
        ctx.db.executemany("DELETE FROM verdict WHERE run_id = ? AND result_id = ? AND verdict_source = 'manual'", [
                           [run_id, r[1]] for r in rows])
        ctx.db.insert_rows(
            "verdict",
            ["run_id", "result_id", "verdict_source", "classification", "kd_code",
                "confidence", "hypothesis", "evidence_json", "created_at"],
            rows,
        )
        ctx.db.commit()
    feedback_dir = ctx.output_dir / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    feedback_path = feedback_dir / f"{run_id}_review_feedback.json"
    with open(feedback_path, "w", encoding="utf-8") as handle:
        json.dump({"run_id": run_id, "workbook": str(path), "agreements": agree,
                  "disagreements": disagree, "items": feedback}, handle, indent=2, default=str)
    final_report = run_report(ctx, run_id, final_review=True) if "xlsx" in ctx.reports.get(
        "formats", ["xlsx", "csv"]) else None
    return {
        "run_id": run_id,
        "reviewed_rows": len(rows),
        "agreements_with_automation": agree,
        "disagreements": disagree,
        "feedback_file": str(feedback_path),
        "final_report": final_report,
        "problems": problems,
    }
