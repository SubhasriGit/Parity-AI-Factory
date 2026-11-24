"""Resumable Project1 task driver with independent middle-task execution."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state" / "task-state.json"
ORDER = ["requirements-confirm", "db-init", "cpp-load", "ims-migrate", "report-parse", "cpp-explode",
         "classify", "llm-review", "human-review-import", "final-report", "validate", "consolidate"]


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    state["last_updated"] = datetime.now(
        timezone.utc).isoformat(timespec="seconds")
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def command_for(task: str, args: argparse.Namespace) -> list[str]:
    python = sys.executable
    if task == "db-init":
        return [python, str(ROOT / "scripts" / "init_database.py"), "--db", str(args.db)]
    if task == "cpp-load":
        cmd = [python, str(ROOT / "scripts" / "load_cpp_snapshot_to_db.py"),
               "--db", str(args.db), "--csv-dir", str(args.cpp_dir)]
        if args.replace:
            cmd.append("--replace")
        if args.only:
            cmd += ["--only", args.only]
        return cmd
    if task == "ims-migrate":
        cmd = [python, str(ROOT / "scripts" / "migrate_ims_snapshot_to_db.py"), "--source",
               str(args.ims_source), "--db", str(args.db), "--day-map", str(args.day_map)]
        if args.refresh:
            cmd.append("--refresh")
        return cmd
    if task == "report-parse":
        cmd = [python, str(ROOT / "pm000003_mismatch_report.py"),
               "--config", str(args.config), "--persist-to-db", str(args.db)]
        if args.analysis_date:
            cmd += ["--analysis-date", args.analysis_date]
        return cmd
    if task == "cpp-explode":
        return [python, str(ROOT / "scripts" / "cpp_analyst.py"), "--db", str(args.db)]
    if task == "classify":
        cmd = [python, str(ROOT / "scripts" / "classify_kd.py"),
               "run", "--db", str(args.db)]
        if args.analysis_date:
            cmd += ["--analysis-date", args.analysis_date]
        return cmd
    if task == "llm-review":
        return [python, str(ROOT / "scripts" / "llm_bridge.py"), "export", "--db", str(args.db), "--output", str(args.llm_candidates)]
    if task == "human-review-import":
        return [python, str(ROOT / "scripts" / "review_and_report.py"), "review-import", "--db", str(args.db), "--file", str(args.reviewed_workbook), "--final-output", str(args.final_workbook)]
    if task == "final-report":
        return [python, str(ROOT / "scripts" / "review_and_report.py"), "report", "--db", str(args.db), "--output", str(args.final_workbook), "--final"]
    if task == "validate":
        return [python, str(ROOT / "scripts" / "validate_outputs.py"), "--db", str(args.db), "--workbook", str(args.final_workbook)]
    if task == "consolidate":
        cmd = [python, str(ROOT / "scripts" / "consolidated_report.py"),
               "--output", str(args.consolidated_workbook)]
        for path in args.consolidate_reports or []:
            cmd += ["--report", str(path)]
        return cmd
    raise ValueError(
        f"Task {task} is not executable or requires only documentation state")


def prerequisites_satisfied(state: dict, task: str) -> bool:
    tasks = state["tasks"]
    if task == "requirements-confirm":
        return True
    index = ORDER.index(task)
    required = ORDER[:index]
    if task == "cpp-load":
        required = ["requirements-confirm", "db-init"]
    elif task == "ims-migrate":
        required = ["requirements-confirm", "db-init"]
    elif task == "report-parse":
        required = ["requirements-confirm", "db-init"]
    elif task == "cpp-explode":
        required = ["cpp-load"]
    elif task == "classify":
        required = ["cpp-load", "ims-migrate", "report-parse", "cpp-explode"]
    elif task == "human-review-import":
        required = ["classify"]
    return all(tasks[item]["status"] == "SUCCESS" for item in required)


def run_task(task: str, args: argparse.Namespace) -> dict:
    state = load_state()
    if not prerequisites_satisfied(state, task):
        state["tasks"][task]["status"] = "BLOCKED"
        save_state(state)
        return {"task": task, "status": "BLOCKED", "reason": "prerequisite evidence is missing"}
    state["tasks"][task]["status"] = "RUNNING"
    save_state(state)
    command = command_for(task, args)
    completed = subprocess.run(command, cwd=str(
        ROOT), text=True, capture_output=True, check=False)
    state = load_state()
    state["tasks"][task]["status"] = "SUCCESS" if completed.returncode == 0 else "FAILED"
    state["tasks"][task]["evidence"] = ["command: " +
                                        " ".join(command), completed.stdout.strip()[-2000:], completed.stderr.strip()[-2000:]]
    if completed.returncode == 0:
        state["overall_status"] = "READY"
    else:
        state["overall_status"] = "FAILED"
    save_state(state)
    print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    return {"task": task, "status": state["tasks"][task]["status"], "returncode": completed.returncode, "command": command}


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("task", "full",
                        "resume", "status"), default="task")
    parser.add_argument("--task", choices=ORDER[1:])
    parser.add_argument("--db", type=Path, default=ROOT /
                        "pm000003_mismatch_analysis.db")
    parser.add_argument("--cpp-dir", type=Path, default=ROOT / "cpp_data")
    parser.add_argument("--only")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--ims-source", type=Path)
    parser.add_argument("--day-map", type=Path)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--config", type=Path,
                        default=ROOT / "config.example.json")
    parser.add_argument("--analysis-date")
    parser.add_argument("--llm-candidates", type=Path,
                        default=ROOT / "output" / "llm_candidates.json")
    parser.add_argument("--reviewed-workbook", type=Path)
    parser.add_argument("--final-workbook", type=Path,
                        default=ROOT / "reports" / "pm000003_final_review.xlsx")
    parser.add_argument("--consolidated-workbook", type=Path,
                        default=ROOT / "reports" / "pm000003_consolidated.xlsx")
    parser.add_argument("--consolidate-reports", nargs="*", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    try:
        state = load_state()
        if args.mode == "status":
            print(json.dumps(state, indent=2))
            return 0
        if args.mode == "task":
            if not args.task:
                raise ValueError("--mode task requires --task")
            result = run_task(args.task, args)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "SUCCESS" else 1
        if args.mode == "resume":
            pending = [task for task in ORDER[1:] if state["tasks"]
                       [task]["status"] != "SUCCESS" and task != "consolidate"]
            selected = pending[:1]
        else:
            selected = [task for task in ORDER[1:] if task != "consolidate"]
        results = []
        for task in selected:
            result = run_task(task, args)
            results.append(result)
            if result["status"] != "SUCCESS":
                print(json.dumps(
                    {"mode": args.mode, "results": results}, indent=2))
                return 1
        print(json.dumps({"mode": args.mode, "results": results}, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
