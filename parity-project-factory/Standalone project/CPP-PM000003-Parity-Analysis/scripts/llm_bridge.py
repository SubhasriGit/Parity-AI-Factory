"""Validated file bridge for the PM000003 LLM second pass."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GUARDRAILS = ROOT / "config" / "llm_guardrails.json"
ALLOWED_CLASSIFICATIONS = {"EXPECTED", "IMS_DATA_ISSUE",
                           "POTENTIAL_ISSUE", "INSUFFICIENT_EVIDENCE"}
BUILTIN_GUARDRAILS = {
    "max_candidates_per_run": 500,
    "max_rows_per_batch": 50,
    "max_batches": 20,
    "max_estimated_cost_per_run": 5.0,
    "redaction": {"enabled": True, "fields": ["store", "offering_number", "deal_number"],
                  "salt_env": "LLM_REDACTION_SALT", "require_salt": False},
    "token_estimation": {"chars_per_token": 4, "prompt_overhead_tokens_per_batch": 400,
                         "assumed_output_tokens_per_candidate": 150},
    "pricing": {"model": "unconfigured", "currency": "USD", "input_per_million": 0.0,
                "cached_per_million": 0.0, "output_per_million": 0.0, "price_source": "TO_BE_CONFIRMED"},
}


def load_guardrails(path: Optional[Path] = None) -> dict:
    config = json.loads(json.dumps(BUILTIN_GUARDRAILS))
    if path is not None and not path.exists():
        raise ValueError(f"Guardrail file not found: {path}")
    source = path or DEFAULT_GUARDRAILS
    if source.exists():
        for key, value in json.loads(source.read_text(encoding="utf-8")).items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    for key in ("max_candidates_per_run", "max_rows_per_batch", "max_batches"):
        if not isinstance(config[key], int) or config[key] < 1:
            raise ValueError(f"guardrail {key} must be a positive integer")
    if config["max_estimated_cost_per_run"] < 0:
        raise ValueError(
            "guardrail max_estimated_cost_per_run must not be negative")
    return config


def estimate_tokens(text: str, chars_per_token: int) -> int:
    return math.ceil(len(text) / max(chars_per_token, 1))


def calculate_cost(pricing: dict, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    uncached = max(input_tokens - cached_tokens, 0)
    return (uncached * pricing["input_per_million"] + cached_tokens * pricing["cached_per_million"]
            + output_tokens * pricing["output_per_million"]) / 1_000_000


def scrub(value, mapping: dict):
    if isinstance(value, str):
        for raw, token in mapping.items():
            value = re.sub(
                rf"(?<![\w.]){re.escape(raw)}(?![\w.])", token, value)
        return value
    if isinstance(value, list):
        return [scrub(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: scrub(item, mapping) for key, item in value.items()}
    return value


def redact_record(record: dict, redaction: dict, salt: str) -> dict:
    mapping = {}
    redacted = dict(record)
    for field in redaction["fields"]:
        raw = str(record.get(field, ""))
        if not raw.strip("0"):
            continue
        token = "h_" + \
            hashlib.sha256(f"{salt}:{field}:{raw}".encode()).hexdigest()[:10]
        mapping[raw] = token
        redacted[field] = token
    redacted["deterministic"] = scrub(record["deterministic"], mapping)
    return redacted


def export_candidates(db_path: Path, output: Path, classifications: tuple = ("POTENTIAL_ISSUE", "IMS_DATA_ISSUE"),
                      guardrails: Optional[dict] = None, estimate_output: Optional[Path] = None) -> dict:
    guardrails = guardrails or load_guardrails()
    redaction = guardrails["redaction"]
    salt = os.environ.get(redaction["salt_env"], "")
    if redaction["enabled"] and redaction["require_salt"] and not salt:
        raise ValueError(
            f"Redaction requires a secret salt in environment variable {redaction['salt_env']}")
    connection = sqlite3.connect(str(db_path))
    try:
        placeholders = ",".join("?" for _ in classifications)
        rows = connection.execute(
            f"SELECT m.row_id,m.day,m.direction,m.store,m.offering_number,m.deal_number,m.price_type,m.effective_date,"
            f"m.dealer_cost_price,m.retail_price,m.casting_price,v.classification,v.kd_code,v.confidence,v.hypothesis,"
            f"v.supporting_evidence,v.missing_evidence FROM mismatch_input m JOIN mismatch_verdict v USING(row_id) "
            f"WHERE v.classification IN ({placeholders}) ORDER BY m.row_id",
            classifications,
        ).fetchall()
        records = []
        for row in rows:
            records.append({
                "row_id": row[0], "day": row[1], "direction": row[2], "store": row[3],
                "offering_number": row[4], "deal_number": row[5], "price_type": row[6],
                "effective_date": row[7], "field_values": {"dealer_cost_price": row[8], "retail_price": row[9], "casting_price": row[10]},
                "deterministic": {"classification": row[11], "kd_code": row[12], "confidence": row[13], "hypothesis": row[14],
                                  "supporting_evidence": json.loads(row[15]), "missing_evidence": json.loads(row[16])},
            })
        estimation, pricing = guardrails["token_estimation"], guardrails["pricing"]
        batch_size = guardrails["max_rows_per_batch"]
        limit = min(guardrails["max_candidates_per_run"],
                    batch_size * guardrails["max_batches"])
        ceiling = guardrails["max_estimated_cost_per_run"]
        kept, record_tokens = [], 0
        skipped_by_limit = skipped_by_budget = 0
        budget_exhausted = False
        for record in records:
            if redaction["enabled"]:
                record = redact_record(record, redaction, salt)
            if len(kept) >= limit:
                skipped_by_limit += 1
                continue
            if budget_exhausted:
                skipped_by_budget += 1
                continue
            tokens = record_tokens + \
                estimate_tokens(json.dumps(record),
                                estimation["chars_per_token"])
            count = len(kept) + 1
            batches = math.ceil(count / batch_size)
            projected = calculate_cost(
                pricing, tokens +
                estimation["prompt_overhead_tokens_per_batch"] * batches,
                estimation["assumed_output_tokens_per_candidate"] * count)
            if projected > ceiling:
                budget_exhausted = True
                skipped_by_budget += 1
                continue
            record_tokens = tokens
            record["batch"] = (count - 1) // batch_size + 1
            kept.append(record)
        batches = math.ceil(len(kept) / batch_size)
        input_tokens = record_tokens + \
            estimation["prompt_overhead_tokens_per_batch"] * batches
        output_tokens = estimation["assumed_output_tokens_per_candidate"] * \
            len(kept)
        estimated_cost = calculate_cost(pricing, input_tokens, output_tokens)
        estimate = {
            "basis": "estimate_not_billed",
            "model": pricing["model"], "currency": pricing["currency"], "price_source": pricing["price_source"],
            "candidates_eligible": len(records), "candidates_exported": len(kept),
            "skipped_by_limit": skipped_by_limit, "skipped_by_budget": skipped_by_budget,
            "batches": batches, "estimated_input_tokens": input_tokens, "estimated_output_tokens": output_tokens,
            "estimated_cost": round(estimated_cost, 6),
            "estimated_cost_per_candidate": round(estimated_cost / len(kept), 6) if kept else 0.0,
            "max_estimated_cost_per_run": ceiling,
            "redaction_enabled": redaction["enabled"], "redacted_fields": redaction["fields"] if redaction["enabled"] else [],
        }
        payload = {"schema_version": 1, "guardrails": {"max_rows_per_batch": batch_size, "batches": batches,
                   "redaction_enabled": redaction["enabled"]}, "records": kept}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        estimate_path = estimate_output or output.parent / \
            "cost" / "llm_cost_estimate.json"
        estimate_path.parent.mkdir(parents=True, exist_ok=True)
        estimate_path.write_text(json.dumps(
            estimate, indent=2), encoding="utf-8")
        return {"output": str(output), "candidates": len(kept), "estimate": str(estimate_path), **{
            key: estimate[key] for key in ("skipped_by_limit", "skipped_by_budget", "batches",
                                           "estimated_input_tokens", "estimated_output_tokens", "estimated_cost")}}
    finally:
        connection.close()


def import_findings(db_path: Path, findings_path: Path) -> dict:
    data = json.loads(findings_path.read_text(encoding="utf-8"))
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ValueError("findings JSON must contain a 'findings' list")
    connection = sqlite3.connect(str(db_path))
    updated = insufficient = ambiguous = rejected = 0
    try:
        for finding in findings:
            row_id = finding.get("row_id")
            classification = str(finding.get("classification", ""))
            if not isinstance(row_id, int) or classification not in ALLOWED_CLASSIFICATIONS:
                rejected += 1
                continue
            current = connection.execute(
                "SELECT classification,kd_code,confidence,hypothesis,supporting_evidence,missing_evidence FROM mismatch_verdict WHERE row_id=?", [row_id]).fetchone()
            if current is None:
                rejected += 1
                continue
            if classification == "INSUFFICIENT_EVIDENCE":
                support = json.loads(current[4])
                missing = list(json.loads(current[5]))
                missing_item = "human approval after LLM insufficient evidence"
                if missing_item not in missing:
                    missing.append(missing_item)
                support["llm_review"] = {
                    "status": "INSUFFICIENT_EVIDENCE",
                    "requires_human_approval": True,
                    "reason": str(finding.get("hypothesis", "LLM could not obtain sufficient evidence")),
                }
                connection.execute(
                    "UPDATE mismatch_verdict SET supporting_evidence=?,missing_evidence=? WHERE row_id=?",
                    [json.dumps(support, sort_keys=True),
                     json.dumps(missing), row_id],
                )
                insufficient += 1
                continue
            support = finding.get("supporting_evidence")
            if not isinstance(support, dict) or not support:
                ambiguous += 1
                continue
            if current[0] == "EXPECTED":
                rejected += 1
                continue
            confidence = float(finding.get("confidence", current[2]))
            if confidence < 0 or confidence > 1:
                rejected += 1
                continue
            missing = list(finding.get(
                "missing_evidence", json.loads(current[5])))
            approval_item = "human approval after LLM insufficient evidence"
            missing = [item for item in missing if item != approval_item]
            support["llm_review"] = {
                "status": "EVIDENCE_REVIEWED",
                "requires_human_approval": False,
            }
            connection.execute(
                "UPDATE mismatch_verdict SET classification=?,kd_code=?,confidence=?,hypothesis=?,supporting_evidence=?,missing_evidence=? WHERE row_id=?",
                [classification, finding.get("kd_code"), confidence, str(finding.get(
                    "hypothesis", current[3])), json.dumps(support, sort_keys=True), json.dumps(missing), row_id],
            )
            updated += 1
        connection.commit()
        return {
            "updated": updated,
            "insufficient_evidence": insufficient,
            "human_approval_required": insufficient,
            "ambiguous": ambiguous,
            "rejected": rejected,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--db", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--guardrails", type=Path,
                        help="Guardrail JSON; defaults to config/llm_guardrails.json")
    export.add_argument("--estimate-output", type=Path)
    importer = sub.add_parser("import")
    importer.add_argument("--db", type=Path, required=True)
    importer.add_argument("--file", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "export":
            result = export_candidates(
                args.db.resolve(), args.output.resolve(), guardrails=load_guardrails(args.guardrails),
                estimate_output=args.estimate_output.resolve() if args.estimate_output else None)
        else:
            result = import_findings(args.db.resolve(), args.file.resolve())
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
