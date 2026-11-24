"""Command line entry point: python scripts/parity.py <command> [options]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .config import ConfigError, load_project
from .pipeline import STAGES, StageFailed, pipeline_stages, run_pipeline, run_stage

HELP = {
    "init-db": "Create the local DB, core tables and empty raw tables (never deletes data)",
    "precheck": "Validate config, input folders/files, packages and DB connectivity",
    "load": "Parse input files into raw_<dataset> tables using each dataset's load policy",
    "filter": "Apply config/filters.json and rebuild flt_<dataset> tables",
    "compare": "Compare configured source vs target data and store results as a new run",
    "ingest-diff": "Convert supplied mismatch files into results as a new run",
    "classify": "Apply rules/known_discrepancies.json to a run",
    "llm-export": "Write unresolved results to output/llm/<run>/batch_*.json for the LLM analyst",
    "llm-import": "Import output/llm/<run>/findings_*.json written by the LLM analyst",
    "report": "Generate Excel/CSV reports for a run",
    "review-import": "Import reviewer columns from a report workbook (manual analysis)",
    "status": "Show datasets, loads, recent runs and verdict distribution",
    "query": "Run one read-only SELECT against the local DB (investigation)",
    "run": "Run the pipeline stages in order (use --from/--to/--skip for partial runs)",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parity", description="Parity project pipeline")
    parser.add_argument("--project-root", default=None,
                        help="Project folder (default: parent of scripts/)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in list(STAGES) + ["run"]:
        p = sub.add_parser(name, help=HELP.get(name, ""),
                           description=HELP.get(name, ""))
        if name in ("load", "filter", "run"):
            p.add_argument("--dataset", action="append",
                           dest="datasets", help="Limit to dataset (repeatable)")
        if name in ("load", "llm-import", "review-import"):
            p.add_argument("--file", action="append", dest="files",
                           help="Explicit file path (repeatable)")
        if name in ("load", "run"):
            p.add_argument("--force", action="store_true",
                           help="Reload files even if an identical file was loaded before")
        if name == "llm-export":
            p.add_argument("--force", action="store_true",
                           help="Re-export even if findings exist (old files are archived)")
        if name in ("classify", "llm-export", "llm-import", "report", "review-import"):
            p.add_argument("--run-id", default=None,
                           help="Run id (default: latest completed run)")
        if name == "query":
            p.add_argument("sql", help="SELECT statement (quote it)")
            p.add_argument("--limit", type=int, default=200,
                           help="Max rows to print (default 200)")
        if name == "run":
            p.add_argument("--workflow", choices=("compare", "ingest-diff"),
                           default=None, help="Entry workflow; required for combined AB projects")
            p.add_argument("--from", dest="start", default=None,
                           help="First stage to run")
            p.add_argument("--to", dest="stop", default=None,
                           help="Last stage to run")
            p.add_argument("--skip", action="append", default=None,
                           help="Stage to skip (repeatable)")
    return parser


def main(argv: Optional[List[str]] = None, project_root: Optional[Path] = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.project_root) if args.project_root else (
        project_root or Path.cwd())
    try:
        ctx = load_project(root)
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}")
        return 2
    kwargs = {k: v for k, v in vars(args).items(
    ) if k not in ("command", "project_root")}
    try:
        if args.command == "run":
            print(
                f"Stages: {' -> '.join(pipeline_stages(ctx, args.workflow, args.start))}")
            run_pipeline(ctx, **kwargs)
        else:
            run_stage(ctx, args.command, **kwargs)
        return 0
    except StageFailed as exc:
        print(str(exc))
        print("Overall status: FAILED")
        return 1
    finally:
        ctx.close()


if __name__ == "__main__":
    sys.exit(main())
