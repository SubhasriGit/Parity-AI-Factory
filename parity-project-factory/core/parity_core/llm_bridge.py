"""Stage 9: hand-off between the deterministic pipeline and the LLM analyst agent.

llm-export writes batches of unresolved results (with KD catalogue and
evidence rows from the local DB) to output/llm/<run_id>/batch_NNN.json.
The LLM analyst agent writes findings_NNN.json next to each batch.
llm-import validates findings and stores them as verdict_source = 'llm'.
`INSUFFICIENT_EVIDENCE` findings leave the deterministic verdict unchanged.

project.json -> llm:
{
  "enabled": true,
  "classifications": ["POTENTIAL_ISSUE"],     verdicts sent to the LLM
  "max_rows_per_batch": 50,
  "max_batches": 20,                          cost guard; null = no limit
  "priority": ["MISMATCH", "MISSING_IN_TARGET", "MISSING_IN_SOURCE"],
  "evidence_queries": [
    {"name": "events", "query": "SELECT * FROM flt_events WHERE sku = :sku LIMIT 20", "params": {"sku": "key.sku"}}
  ]
}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .classify import final_verdicts
from .conditions import get_path
from .config import ProjectContext
from .db import named_to_positional, q
from .ingest import utc_now
from .results import load_result_record, resolve_run_id

INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


def llm_dir(ctx: ProjectContext, run_id: str) -> Path:
    return ctx.output_dir / "llm" / run_id


def _evidence(ctx: ProjectContext, record: dict) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in ctx.llm.get("evidence_queries", []) or []:
        params = {}
        skip = False
        for name, path in (item.get("params") or {}).items():
            value = get_path(record, path)
            if value is None:
                skip = True
                break
            params[name] = value
        if skip:
            out[item["name"]] = "skipped: parameter missing on this record"
            continue
        sql, values = named_to_positional(item["query"], params)
        cursor = ctx.db.execute(sql, values)
        cols = [d[0] for d in cursor.description]
        out[item["name"]] = [dict(zip(cols, map(lambda v: None if v is None else str(v), r))) for r in cursor.fetchall()]
    return out


def kd_catalogue(ctx: ProjectContext) -> List[dict]:
    return [
        {
            "code": r.get("code"),
            "title": r.get("title"),
            "classification": r.get("classification"),
            "description": r.get("description"),
            "evidence_needed": r.get("evidence_needed"),
        }
        for r in ctx.rules.get("rules", [])
        if r.get("enabled", True)
    ]


def run_llm_export(ctx: ProjectContext, run_id: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    run_id = resolve_run_id(ctx, run_id)
    cfg = ctx.llm
    if not cfg.get("enabled", True):
        return {"run_id": run_id, "status": "SKIPPED", "reason": "llm.enabled is false in config/project.json"}
    target_dir = llm_dir(ctx, run_id)
    existing_findings = sorted(target_dir.glob("findings_*.json")) if target_dir.exists() else []
    if existing_findings and not force:
        raise RuntimeError(
            f"{target_dir} already contains findings files. Import them with 'llm-import' or re-export with --force "
            f"(old batch/findings files will be moved to an archive folder)."
        )
    if target_dir.exists():
        archive = target_dir / f"archive_{utc_now().replace(':', '')}"
        for old in list(target_dir.glob("batch_*.json")) + existing_findings:
            archive.mkdir(parents=True, exist_ok=True)
            old.rename(archive / old.name)
    target_dir.mkdir(parents=True, exist_ok=True)

    wanted = set(cfg.get("classifications", ["POTENTIAL_ISSUE"]))
    verdicts = final_verdicts(ctx, run_id)
    candidate_ids = [rid for rid, v in verdicts.items() if v["classification"] in wanted and v["verdict_source"] != "manual"]
    if not verdicts:
        raise RuntimeError("No verdicts for this run. Run the 'classify' stage first.")
    priority = cfg.get("priority", ["MISMATCH", "MISSING_IN_TARGET", "MISSING_IN_SOURCE"])

    records = []
    id_set = set(candidate_ids)
    for row in ctx.db.iter_query("SELECT * FROM parity_result WHERE run_id = ? ORDER BY result_id", [run_id]):
        if row["result_id"] in id_set:
            records.append(load_result_record(row))
    records.sort(key=lambda r: (priority.index(r["result_type"]) if r["result_type"] in priority else len(priority), r["result_id"]))

    per_batch = int(cfg.get("max_rows_per_batch", 50))
    max_batches = cfg.get("max_batches")
    batches = [records[i : i + per_batch] for i in range(0, len(records), per_batch)]
    not_exported = 0
    if max_batches is not None and len(batches) > int(max_batches):
        not_exported = sum(len(b) for b in batches[int(max_batches):])
        batches = batches[: int(max_batches)]

    catalogue = kd_catalogue(ctx)
    files = []
    for number, batch in enumerate(batches, start=1):
        payload = {
            "run_id": run_id,
            "batch": number,
            "instructions": "Analyse each record; write findings_%03d.json in this folder following findings_schema in this file." % number,
            "classifications": ctx.rules.get("classifications", {}),
            "known_discrepancies": catalogue,
            "findings_schema": {
                "run_id": run_id,
                "batch": number,
                "findings": [
                    {
                        "result_id": "<int from records>",
                        "classification": "one of classifications keys or INSUFFICIENT_EVIDENCE",
                        "kd_code": "<known discrepancy code or null>",
                        "confidence": "<0.0-1.0>",
                        "hypothesis": "<one-sentence root cause>",
                        "evidence": "<facts from the record/evidence that support it>",
                        "verification_steps": "<what a QA should check to confirm>",
                    }
                ],
            },
            "records": [
                {
                    **record,
                    "current_verdict": {
                        k: verdicts[record["result_id"]].get(k)
                        for k in ("verdict_source", "classification", "kd_code", "confidence", "hypothesis")
                    },
                    "evidence_data": _evidence(ctx, record),
                }
                for record in batch
            ],
        }
        path = target_dir / f"batch_{number:03d}.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
        files.append(str(path))
    return {
        "run_id": run_id,
        "status": "EXPORTED" if files else "NOTHING_TO_ANALYSE",
        "candidates": len(records) + not_exported,
        "exported_rows": sum(len(b) for b in batches),
        "not_exported_due_to_max_batches": not_exported,
        "batch_files": files,
        "folder": str(target_dir),
    }


def run_llm_import(ctx: ProjectContext, run_id: Optional[str] = None, files: Optional[List[str]] = None) -> Dict[str, Any]:
    run_id = resolve_run_id(ctx, run_id)
    folder = llm_dir(ctx, run_id)
    paths = [Path(f) for f in files] if files else sorted(folder.glob("findings_*.json"))
    if not paths:
        raise RuntimeError(f"No findings_*.json files in {folder}. The LLM analyst agent must write them first.")
    allowed = set((ctx.rules.get("classifications") or {}).keys()) | {INSUFFICIENT}
    codes = {r.get("code") for r in ctx.rules.get("rules", [])}
    valid_ids = {r[0] for r in ctx.db.query("SELECT result_id FROM parity_result WHERE run_id = ?", [run_id])}

    unchanged = 0
    problems: List[str] = []
    rows: List[list] = []
    seen = set()
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}: invalid JSON ({exc})")
            continue
        if data.get("run_id") not in (None, run_id):
            problems.append(f"{path.name}: run_id {data.get('run_id')} does not match {run_id}")
            continue
        for i, finding in enumerate(data.get("findings", [])):
            where = f"{path.name} findings[{i}]"
            try:
                result_id = int(finding.get("result_id"))
            except (TypeError, ValueError):
                problems.append(f"{where}: result_id missing or not an integer")
                continue
            if result_id not in valid_ids:
                problems.append(f"{where}: result_id {result_id} is not in run {run_id}")
                continue
            classification = finding.get("classification")
            if classification not in allowed:
                problems.append(f"{where}: classification '{classification}' not allowed ({sorted(allowed)})")
                continue
            if classification == INSUFFICIENT:
                unchanged += 1
                continue
            kd = finding.get("kd_code") or None
            if kd and kd not in codes:
                problems.append(f"{where}: unknown kd_code '{kd}' (kept, but add it to rules/known_discrepancies.json if it is a new pattern)")
            try:
                confidence = float(finding.get("confidence", 0))
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))
            evidence = {
                "evidence": finding.get("evidence"),
                "verification_steps": finding.get("verification_steps"),
                "findings_file": path.name,
            }
            if result_id in seen:
                problems.append(f"{where}: duplicate finding for result_id {result_id}; last one wins")
            seen.add(result_id)
            rows.append([run_id, result_id, "llm", classification, kd, confidence, finding.get("hypothesis", ""), json.dumps(evidence, default=str), utc_now()])

    final: Dict[int, list] = {r[1]: r for r in rows}
    if final:
        ctx.db.executemany("DELETE FROM verdict WHERE run_id = ? AND result_id = ? AND verdict_source = 'llm'", [[run_id, rid] for rid in final])
        ctx.db.insert_rows(
            "verdict",
            ["run_id", "result_id", "verdict_source", "classification", "kd_code", "confidence", "hypothesis", "evidence_json", "created_at"],
            list(final.values()),
        )
        ctx.db.commit()
    return {
        "run_id": run_id,
        "files": [p.name for p in paths],
        "verdicts_updated": len(final),
        "left_unchanged_insufficient_evidence": unchanged,
        "problems": problems,
    }
