"""Stage 8: deterministic classification of parity results.

rules/known_discrepancies.json:
{
  "classifications": {"EXPECTED": "...", "DATA_ISSUE": "...", "POTENTIAL_ISSUE": "..."},
  "default": {"classification": "POTENTIAL_ISSUE", "hypothesis": "No known discrepancy pattern matched"},
  "rules": [
    {
      "code": "KD-1", "title": "...", "description": "business explanation",
      "classification": "EXPECTED", "priority": 10, "confidence": 0.9, "enabled": true,
      "applies_to": ["MISMATCH"],
      "when": {condition on the result record},
      "sql_check": {"query": "SELECT 1 FROM flt_events WHERE sku = :sku", "params": {"sku": "key.sku"}, "expect": "exists"},
      "python_check": "function_name_in_rules/custom_rules.py",
      "hypothesis": "Text; {key.sku} style placeholders are filled from the record",
      "evidence_needed": "what a reviewer should check to confirm"
    }
  ]
}
Rules are evaluated by ascending priority; the first rule whose every check
passes wins. Results no rule explains get the default verdict, which makes
them candidates for the LLM analysis stage.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .conditions import evaluate, get_path
from .config import ProjectContext
from .db import named_to_positional
from .ingest import utc_now
from .results import load_result_record, resolve_run_id

PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_.]+)\}")


def render(template: str, record: dict) -> str:
    def repl(match: "re.Match[str]") -> str:
        value = get_path(record, match.group(1))
        if isinstance(value, list):
            return ", ".join(map(str, value))
        return "" if value is None else str(value)

    return PLACEHOLDER.sub(repl, template or "")


def _load_custom_rules(ctx: ProjectContext) -> Dict[str, Callable]:
    path = ctx.root / "rules" / "custom_rules.py"
    if not path.exists():
        return {}
    spec = importlib.util.spec_from_file_location("custom_rules", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return {name: getattr(module, name) for name in dir(module) if callable(getattr(module, name)) and not name.startswith("_")}


def sorted_rules(ctx: ProjectContext) -> List[dict]:
    rules = [r for r in ctx.rules.get("rules", []) if r.get("enabled", True)]
    return sorted(rules, key=lambda r: (r.get("priority", 1000), r.get("code", "")))


def _sql_check(ctx: ProjectContext, check: dict, record: dict) -> Optional[dict]:
    params = {}
    for name, path in (check.get("params") or {}).items():
        value = get_path(record, path)
        if value is None:
            return None
        params[name] = value
    sql, values = named_to_positional(check["query"], params)
    rows = ctx.db.query(sql, values)
    expect = check.get("expect", "exists")
    passed = bool(rows) if expect == "exists" else not rows
    if not passed:
        return None
    return {"query_rows": len(rows), "sample": [list(map(str, r)) for r in rows[:3]]}


def classify_record(ctx: ProjectContext, record: dict, rules: List[dict], custom: Dict[str, Callable]) -> dict:
    for rule in rules:
        applies = rule.get("applies_to")
        if applies and record["result_type"] not in applies:
            continue
        if "when" in rule and not evaluate(rule["when"], record):
            continue
        evidence: Dict[str, Any] = {"rule": rule["code"]}
        if rule.get("sql_check"):
            sql_evidence = _sql_check(ctx, rule["sql_check"], record)
            if sql_evidence is None:
                continue
            evidence["sql_check"] = sql_evidence
        hypothesis = rule.get("hypothesis") or rule.get("title", "")
        confidence = rule.get("confidence", 1.0)
        if rule.get("python_check"):
            fn = custom.get(rule["python_check"])
            if fn is None:
                raise RuntimeError(f"Rule {rule['code']}: python_check '{rule['python_check']}' not found in rules/custom_rules.py")
            outcome = fn(record, ctx.db)
            if not outcome:
                continue
            if isinstance(outcome, dict):
                hypothesis = outcome.get("hypothesis", hypothesis)
                confidence = outcome.get("confidence", confidence)
                evidence["python_check"] = outcome.get("evidence")
        return {
            "classification": rule["classification"],
            "kd_code": rule["code"],
            "confidence": confidence,
            "hypothesis": render(hypothesis, record),
            "evidence": evidence,
        }
    default = ctx.rules.get("default", {})
    return {
        "classification": default.get("classification", "POTENTIAL_ISSUE"),
        "kd_code": None,
        "confidence": default.get("confidence", 0.0),
        "hypothesis": render(default.get("hypothesis", "No known discrepancy pattern matched"), record),
        "evidence": {"rule": None, "evidence_needed": default.get("evidence_needed", "")},
    }


def run_classify(ctx: ProjectContext, run_id: Optional[str] = None) -> Dict[str, Any]:
    db = ctx.db
    run_id = resolve_run_id(ctx, run_id)
    rules = sorted_rules(ctx)
    custom = _load_custom_rules(ctx)
    db.execute("DELETE FROM verdict WHERE run_id = ? AND verdict_source = 'rule'", [run_id])
    columns = ["run_id", "result_id", "verdict_source", "classification", "kd_code", "confidence", "hypothesis", "evidence_json", "created_at"]
    buffer: List[list] = []
    distribution: Dict[str, int] = {}
    total = 0
    now = utc_now()
    for row in db.iter_query("SELECT * FROM parity_result WHERE run_id = ? ORDER BY result_id", [run_id], batch_size=ctx.batch_size):
        record = load_result_record(row)
        verdict = classify_record(ctx, record, rules, custom)
        buffer.append([
            run_id, record["result_id"], "rule", verdict["classification"], verdict["kd_code"],
            verdict["confidence"], verdict["hypothesis"], json.dumps(verdict["evidence"], default=str), now,
        ])
        label = f"{verdict['classification']} / {verdict['kd_code'] or '-'}"
        distribution[label] = distribution.get(label, 0) + 1
        total += 1
        if len(buffer) >= ctx.batch_size:
            db.insert_rows("verdict", columns, buffer)
            buffer = []
    db.insert_rows("verdict", columns, buffer)
    db.commit()
    return {"run_id": run_id, "classified": total, "distribution": dict(sorted(distribution.items(), key=lambda kv: -kv[1]))}


PRECEDENCE = {"manual": 3, "llm": 2, "rule": 1}


def final_verdicts(ctx: ProjectContext, run_id: str) -> Dict[int, dict]:
    """Best verdict per result: manual review > LLM analysis > deterministic rule."""
    best: Dict[int, dict] = {}
    for row in ctx.db.iter_query("SELECT * FROM verdict WHERE run_id = ?", [run_id], batch_size=ctx.batch_size):
        current = best.get(row["result_id"])
        if current is None or PRECEDENCE.get(row["verdict_source"], 0) > PRECEDENCE.get(current["verdict_source"], 0):
            best[row["result_id"]] = row
    return best


def all_verdicts(ctx: ProjectContext, run_id: str) -> Dict[int, Dict[str, dict]]:
    out: Dict[int, Dict[str, dict]] = {}
    for row in ctx.db.iter_query("SELECT * FROM verdict WHERE run_id = ?", [run_id], batch_size=ctx.batch_size):
        out.setdefault(row["result_id"], {})[row["verdict_source"]] = row
    return out
