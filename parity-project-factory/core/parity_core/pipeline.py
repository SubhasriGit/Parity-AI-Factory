"""Stage registry, prechecks, status and the full-run driver."""

from __future__ import annotations

import importlib
import json
import sys
from typing import Any, Callable, Dict, List, Optional

from . import __version__
from .config import ProjectContext, get_logger, validate_project
from .connectors import get_connector
from .db import q
from .ingest import ensure_raw_table, load_dataset, utc_now

STAGES_COMMON = ["init-db", "precheck", "load", "filter"]
STAGES_ANALYSIS = ["classify", "llm-export", "report"]
STAGES_A = STAGES_COMMON + ["compare"] + STAGES_ANALYSIS
STAGES_B = STAGES_COMMON + ["ingest-diff"] + STAGES_ANALYSIS


class StageFailed(Exception):
    pass


def stage_init_db(ctx: ProjectContext, **_: Any) -> Dict[str, Any]:
    db = ctx.db
    created = []
    for ds in ctx.datasets.values():
        existed = db.table_exists(ds.raw_table)
        ensure_raw_table(db, ds)
        if not existed:
            created.append(ds.raw_table)
    db.set_meta("project.name", ctx.project.get("name"))
    db.set_meta("project.mode", ctx.mode)
    db.set_meta("parity_core.version", __version__)
    if not db.get_meta("db.created_at"):
        db.set_meta("db.created_at", utc_now())
    db.commit()
    return {
        "database": str(db.path),
        "engine": db.engine,
        "created_tables": created,
        "table_rows": {ds.raw_table: db.count(ds.raw_table) for ds in ctx.datasets.values()},
        "note": "Existing data is never deleted by init-db.",
    }


def stage_precheck(ctx: ProjectContext, **_: Any) -> Dict[str, Any]:
    problems = validate_project(ctx)
    warnings: List[str] = []
    connectors = []
    schema = {}
    expected_meta = {"_rid", "_load_id",
                     "_source_file", "_line_no", "_row_hash"}
    for dataset in ctx.datasets.values():
        expected = expected_meta | set(dataset.columns)
        if not ctx.db.table_exists(dataset.raw_table):
            problems.append(
                f"database schema: raw table '{dataset.raw_table}' is missing; run 'init-db'")
            schema[dataset.name] = {
                "table": dataset.raw_table, "exists": False, "columns": []}
            continue
        actual = set(ctx.db.columns(dataset.raw_table))
        missing = sorted(expected - actual)
        if missing:
            problems.append(
                f"database schema: table '{dataset.raw_table}' is missing columns {missing}; run 'init-db' and verify the mapping")
        schema[dataset.name] = {
            "table": dataset.raw_table,
            "exists": True,
            "mapped_columns": len(dataset.columns),
            "missing_columns": missing,
        }
    for ds in ctx.datasets.values():
        try:
            connector = get_connector(ds.name, ds.connector, ctx.root)
            info = connector.check()
            if not info["folder_exists"]:
                problems.append(
                    f"dataset '{ds.name}': folder {info['folder']} does not exist")
            elif not info["matching_files"]:
                loaded = ctx.db.scalar(
                    "SELECT COUNT(*) FROM _loads WHERE dataset = ? AND status='OK'", [ds.name])
                message = f"dataset '{ds.name}': no files matching '{info['pattern']}' in {info['folder']}"
                (warnings if loaded else problems).append(message +
                                                          (" (previous loads exist in DB)" if loaded else ""))
            connectors.append(info)
        except (NotImplementedError, ValueError) as exc:
            problems.append(str(exc))
    for module in ("pandas", "openpyxl"):
        try:
            importlib.import_module(module)
        except ImportError:
            problems.append(
                f"Python package '{module}' is not installed (pip install -r requirements.txt)")
    try:
        ctx.db.scalar("SELECT 1")
    except Exception as exc:  # pragma: no cover - defensive
        problems.append(f"Database connection failed: {exc}")
    result = {"config_valid": not problems, "problems": problems,
              "warnings": warnings, "database_schema": schema, "inputs": connectors}
    if problems:
        raise StageFailed(json.dumps(result, indent=2))
    return result


def stage_load(ctx: ProjectContext, datasets: Optional[List[str]] = None, files: Optional[List[str]] = None, force: bool = False, **_: Any) -> Dict[str, Any]:
    targets = [ctx.dataset(n) for n in datasets] if datasets else list(
        ctx.datasets.values())
    if files and len(targets) != 1:
        raise StageFailed(
            "--file can only be used together with exactly one --dataset")
    batch = ctx.db.next_id("_loads", "load_batch")
    out = []
    for ds in targets:
        out.extend(load_dataset(ctx, ds, files=files,
                   force=force, load_batch=batch))
    return {"loads": out}


def stage_filter(ctx: ProjectContext, datasets: Optional[List[str]] = None, **_: Any) -> Dict[str, Any]:
    from .filtering import filter_all

    return {"filters": filter_all(ctx, datasets)}


def stage_compare(ctx: ProjectContext, **_: Any) -> Dict[str, Any]:
    if "A" not in ctx.mode:
        raise StageFailed(
            "'compare' is unavailable because this project has no source/target comparison workflow")
    from .compare import run_compare

    return run_compare(ctx)


def stage_ingest_diff(ctx: ProjectContext, **_: Any) -> Dict[str, Any]:
    if "B" not in ctx.mode:
        raise StageFailed(
            "'ingest-diff' is unavailable because this project has no supplied-report workflow")
    from .diff_ingest import run_ingest_diff

    return run_ingest_diff(ctx)


def stage_classify(ctx: ProjectContext, run_id: Optional[str] = None, **_: Any) -> Dict[str, Any]:
    from .classify import run_classify

    missing = []
    for snapshot in ctx.analysis_snapshots.get("analysis_snapshots", []) or []:
        if not snapshot.get("required_for_analysis", True):
            continue
        dataset = ctx.dataset(snapshot["dataset"])
        table = dataset.filtered_table
        if not ctx.db.table_exists(table):
            missing.append(
                f"snapshot '{snapshot.get('name', dataset.name)}': filtered table '{table}' is missing; run load and filter")
        elif ctx.db.count(table) == 0:
            missing.append(
                f"snapshot '{snapshot.get('name', dataset.name)}': table '{table}' has no rows")
    if missing:
        raise StageFailed(
            "Required analysis snapshot precheck failed:\n  - " + "\n  - ".join(missing))
    return run_classify(ctx, run_id)


def stage_llm_export(ctx: ProjectContext, run_id: Optional[str] = None, force: bool = False, **_: Any) -> Dict[str, Any]:
    from .llm_bridge import run_llm_export

    return run_llm_export(ctx, run_id, force=force)


def stage_llm_import(ctx: ProjectContext, run_id: Optional[str] = None, files: Optional[List[str]] = None, **_: Any) -> Dict[str, Any]:
    from .llm_bridge import run_llm_import

    return run_llm_import(ctx, run_id, files)


def stage_report(ctx: ProjectContext, run_id: Optional[str] = None, **_: Any) -> Dict[str, Any]:
    from .report import run_report

    return run_report(ctx, run_id)


def stage_review_import(ctx: ProjectContext, run_id: Optional[str] = None, files: Optional[List[str]] = None, **_: Any) -> Dict[str, Any]:
    from .report import run_review_import

    if not files or len(files) != 1:
        raise StageFailed(
            "review-import needs exactly one --file <reviewed workbook.xlsx>")
    return run_review_import(ctx, files[0], run_id)


def stage_status(ctx: ProjectContext, **_: Any) -> Dict[str, Any]:
    db = ctx.db
    datasets = {}
    for ds in ctx.datasets.values():
        datasets[ds.name] = {
            "role": ds.role,
            "raw_rows": db.count(ds.raw_table) if db.table_exists(ds.raw_table) else None,
            "filtered_rows": db.count(ds.filtered_table) if db.table_exists(ds.filtered_table) else None,
            "last_source_file": db.get_meta(f"{ds.name}.last_source_file"),
            "last_loaded_at": db.get_meta(f"{ds.name}.last_loaded_at"),
        }
    runs = [
        {"run_id": r[0], "mode": r[1], "started_at": r[2], "status": r[3],
            "results": json.loads(r[4] or "{}").get("results_by_type")}
        for r in db.query("SELECT run_id, mode, started_at, status, stats_json FROM parity_run ORDER BY started_at DESC LIMIT 10")
    ]
    latest = runs[0]["run_id"] if runs else None
    verdicts = {}
    if latest:
        for r in db.query(
            "SELECT verdict_source, classification, COALESCE(kd_code,'-'), COUNT(*) FROM verdict WHERE run_id = ? GROUP BY 1,2,3 ORDER BY 1,4 DESC",
            [latest],
        ):
            verdicts.setdefault(r[0], {})[f"{r[1]} / {r[2]}"] = r[3]
    return {
        "project": ctx.project.get("name"),
        "mode": ctx.mode,
        "database": str(db.path),
        "parity_core_version": __version__,
        "datasets": datasets,
        "recent_runs": runs,
        "latest_run_verdicts": verdicts,
    }


def stage_query(ctx: ProjectContext, sql: Optional[str] = None, limit: int = 200, **_: Any) -> Dict[str, Any]:
    text = (sql or "").strip().rstrip(";")
    lowered = text.lower()
    if not (lowered.startswith("select") or lowered.startswith("with") or lowered.startswith("pragma table_info")):
        raise StageFailed(
            "query only accepts read-only SELECT / WITH statements")
    if ";" in text:
        raise StageFailed("query accepts a single statement")
    import re as _re

    if _re.search(r"\b(insert|update|delete|drop|alter|create|attach|detach|replace|vacuum|copy|export)\b", lowered):
        raise StageFailed(
            "query is read-only: data-changing keywords are not allowed")
    cursor = ctx.db.execute(text)
    columns = [d[0] for d in cursor.description] if cursor.description else []
    rows = cursor.fetchmany(int(limit) + 1)
    truncated = len(rows) > int(limit)
    return {
        "columns": columns,
        "rows": [[None if v is None else str(v) for v in r] for r in rows[: int(limit)]],
        "truncated": truncated,
    }


STAGES: Dict[str, Callable[..., Dict[str, Any]]] = {
    "init-db": stage_init_db,
    "precheck": stage_precheck,
    "load": stage_load,
    "filter": stage_filter,
    "compare": stage_compare,
    "ingest-diff": stage_ingest_diff,
    "classify": stage_classify,
    "llm-export": stage_llm_export,
    "llm-import": stage_llm_import,
    "report": stage_report,
    "review-import": stage_review_import,
    "status": stage_status,
    "query": stage_query,
}


def pipeline_stages(ctx: ProjectContext, workflow: Optional[str] = None, start: Optional[str] = None) -> List[str]:
    if ctx.mode == "AB":
        if workflow == "compare":
            stages = list(STAGES_A)
        elif workflow == "ingest-diff":
            stages = list(STAGES_B)
        elif start in STAGES_ANALYSIS:
            stages = STAGES_COMMON + list(STAGES_ANALYSIS)
        else:
            raise StageFailed(
                "Combined projects require --workflow compare or --workflow ingest-diff unless --from selects classify, llm-export, or report")
    elif workflow and workflow not in ("compare", "ingest-diff"):
        raise StageFailed("--workflow must be 'compare' or 'ingest-diff'")
    else:
        expected = "compare" if ctx.mode == "A" else "ingest-diff"
        if workflow and workflow != expected:
            raise StageFailed(
                f"This project uses workflow '{expected}', not '{workflow}'")
        stages = list(STAGES_A if ctx.mode == "A" else STAGES_B)
    if not ctx.llm.get("enabled", True):
        stages.remove("llm-export")
    return stages


def run_stage(ctx: ProjectContext, name: str, emit: Callable[[str], None] = print, **kwargs: Any) -> Dict[str, Any]:
    logger = get_logger(ctx)
    logger.info("stage %s started args=%s", name, {
                k: v for k, v in kwargs.items() if v})
    try:
        result = STAGES[name](ctx, **kwargs)
    except Exception as exc:
        logger.exception("stage %s failed", name)
        emit(f"== STAGE {name}: FAILED")
        emit(str(exc))
        raise StageFailed(str(exc)) from exc
    logger.info("stage %s finished", name)
    emit(f"== STAGE {name}: OK")
    emit(json.dumps(result, indent=2, default=str))
    return result


def run_pipeline(
    ctx: ProjectContext,
    start: Optional[str] = None,
    stop: Optional[str] = None,
    skip: Optional[List[str]] = None,
    workflow: Optional[str] = None,
    emit: Callable[[str], None] = print,
    **kwargs: Any,
) -> Dict[str, Any]:
    stages = pipeline_stages(ctx, workflow, start)
    for marker in (start, stop):
        if marker and marker not in stages:
            raise StageFailed(
                f"Unknown stage '{marker}' for this project. Stages: {', '.join(stages)}")
    if start:
        stages = stages[stages.index(start):]
    if stop:
        stages = stages[: stages.index(stop) + 1]
    skip = skip or []
    summary = {}
    for name in stages:
        if name in skip:
            emit(f"== STAGE {name}: SKIPPED (requested)")
            summary[name] = "SKIPPED"
            continue
        stage_kwargs = dict(kwargs)
        if name in ("compare", "ingest-diff"):
            stage_kwargs.pop("run_id", None)
        if name != "load":
            stage_kwargs.pop("force", None)
        run_stage(ctx, name, emit=emit, **stage_kwargs)
        summary[name] = "OK"
    emit("Overall status: SUCCESS")
    return summary
