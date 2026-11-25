"""Validated file bridge for the PM000003 LLM second pass."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Optional

ALLOWED_CLASSIFICATIONS = {"EXPECTED", "IMS_DATA_ISSUE",
                           "POTENTIAL_ISSUE", "INSUFFICIENT_EVIDENCE"}


def export_candidates(db_path: Path, output: Path, classifications: tuple = ("POTENTIAL_ISSUE", "IMS_DATA_ISSUE")) -> dict:
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
        payload = {"schema_version": 1, "records": records}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {"output": str(output), "candidates": len(records)}
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
    importer = sub.add_parser("import")
    importer.add_argument("--db", type=Path, required=True)
    importer.add_argument("--file", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    try:
        result = export_candidates(args.db.resolve(), args.output.resolve(
        )) if args.command == "export" else import_findings(args.db.resolve(), args.file.resolve())
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
