"""Resumable CPP task driver with independent middle-task execution."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state" / "task-state.json"
POLICY_PATH = ROOT / "config" / "pipeline.yaml"
DEFAULT_MAX_RETRIES = 2
ORDER = ["requirements-confirm", "db-init", "cpp-load", "ims-migrate", "report-parse", "cpp-explode",
         "classify", "llm-review", "human-review-import", "final-report", "validate", "consolidate"]


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    state["last_updated"] = datetime.now(
        timezone.utc).isoformat(timespec="seconds")
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def configured_max_retries() -> int:
    if not POLICY_PATH.exists():
        return DEFAULT_MAX_RETRIES
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")) or {}
    value = policy.get("execution_policy", {}).get(
        "max_retries", DEFAULT_MAX_RETRIES)
    if not isinstance(value, int) or value < 0:
        raise ValueError(
            "execution_policy.max_retries must be a non-negative integer")
    return value


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
    max_retries = args.max_retries if args.max_retries is not None else configured_max_retries()
    if max_retries < 0:
        raise ValueError("--max-retries must be zero or greater")
    completed = None
    attempts = []
    for attempt in range(1, max_retries + 2):
        try:
            completed = subprocess.run(command, cwd=str(
                ROOT), text=True, capture_output=True, check=False)
            attempts.append({
                "attempt": attempt,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip()[-2000:],
                "stderr": completed.stderr.strip()[-2000:],
            })
            if completed.returncode == 0:
                break
        except OSError as exc:
            attempts.append({
                "attempt": attempt,
                "returncode": 1,
                "stdout": "",
                "stderr": str(exc),
            })
    state = load_state()
    state_task = state["tasks"][task]
    state_task["attempts"] = len(attempts)
    state_task["max_retries"] = max_retries
    state_task["evidence"] = [{"command": command}, *attempts]
    state_task["human_inspection_required"] = completed is None or completed.returncode != 0
    if completed is not None and completed.returncode == 0:
        state_task["status"] = "SUCCESS"
        state["overall_status"] = "READY"
    else:
        state_task["status"] = "HUMAN_INSPECTION_REQUIRED"
        state["overall_status"] = "HUMAN_INSPECTION_REQUIRED"
    save_state(state)
    if attempts:
        final_attempt = attempts[-1]
        print(final_attempt["stdout"], end="")
        if final_attempt["stderr"]:
            print(final_attempt["stderr"], file=sys.stderr, end="")
    return {
        "task": task,
        "status": state_task["status"],
        "attempts": len(attempts),
        "max_retries": max_retries,
        "human_inspection_required": state_task["human_inspection_required"],
        "returncode": 0 if state_task["status"] == "SUCCESS" else 1,
        "command": command,
    }


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
    parser.add_argument("--max-retries", type=int, default=None,
                        help="Override the configured retry limit; each retry is an additional attempt")
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
            inspection_required = [
                task for task in ORDER[1:]
                if state["tasks"][task]["status"] == "HUMAN_INSPECTION_REQUIRED"
            ]
            if inspection_required:
                print(json.dumps({
                    "mode": args.mode,
                    "status": "HUMAN_INSPECTION_REQUIRED",
                    "tasks": inspection_required,
                    "reason": "A human must inspect the recorded attempts before explicitly rerunning the task.",
                }, indent=2))
                return 1
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
