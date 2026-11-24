"""End-to-end and unit tests for the Parity Project Factory.

Run: python -m unittest discover -s tests -v   (from the factory root)
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

FACTORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FACTORY_ROOT / "core"))
sys.path.insert(0, str(FACTORY_ROOT / "factory"))

import new_project  # noqa: E402
from parity_core.cli import main as parity_main  # noqa: E402
from parity_core.conditions import evaluate  # noqa: E402
from parity_core.normalize import normalize, values_equal  # noqa: E402

EXAMPLE_A = FACTORY_ROOT / "examples" / "mode-a-price-compare" / "spec.json"
EXAMPLE_B = FACTORY_ROOT / "examples" / "mode-b-mismatch-report" / "spec.json"


def run_cli(project: Path, *args: str) -> tuple:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = parity_main(list(args), project_root=project)
    return code, buffer.getvalue()


def db_rows(project: Path, sql: str, params=()) -> list:
    conn = sqlite3.connect(str(project / "db" / "parity.db"))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


class GeneratedProjectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="parity_factory_test_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def generate(self, spec: Path, name: str) -> Path:
        dest = self.tmp / name
        result = new_project.generate(spec, dest, with_samples=True)
        self.assertEqual(result["problems"], [])
        return dest

    def latest_run(self, project: Path) -> str:
        return db_rows(project, "SELECT run_id FROM parity_run ORDER BY started_at DESC, run_id DESC LIMIT 1")[0][0]

    def verdicts(self, project: Path, run_id: str, source: str = "rule") -> dict:
        rows = db_rows(
            project,
            "SELECT r.record_key, v.classification, v.kd_code FROM verdict v JOIN parity_result r "
            "ON r.run_id = v.run_id AND r.result_id = v.result_id WHERE v.run_id = ? AND v.verdict_source = ?",
            (run_id, source),
        )
        return {key: (cls, kd) for key, cls, kd in rows}

    # -- Mode A -----------------------------------------------------------
    def test_mode_a_full_cycle_with_llm_and_review(self) -> None:
        project = self.generate(EXAMPLE_A, "mode_a")
        self.assertTrue((project / ".github" / "agents" /
                        "price-compare-demo-comparator.agent.md").exists())
        self.assertFalse((project / ".github" / "agents" /
                         "price-compare-demo-diff-ingestor.agent.md").exists())

        code, out = run_cli(project, "run")
        self.assertEqual(code, 0, out)
        run_id = self.latest_run(project)
        mismatch_report = project / "output" / "reports" / \
            f"price-compare-demo_mismatch_report_{run_id}.csv"
        self.assertTrue(mismatch_report.exists())
        counts = dict(db_rows(
            project, "SELECT result_type, COUNT(*) FROM parity_result WHERE run_id = ? GROUP BY 1", (run_id,)))
        self.assertEqual(
            counts, {"MISMATCH": 3, "MISSING_IN_TARGET": 1, "MISSING_IN_SOURCE": 1})
        verdicts = self.verdicts(project, run_id)
        # dealer price 0 in legacy
        self.assertEqual(verdicts["0002|1005"], ("EXPECTED", "KD-1"))
        # ADD event in reference data
        self.assertEqual(verdicts["0001|1003"], ("EXPECTED", "KD-2"))
        # date shifted by one day
        self.assertEqual(verdicts["0001|1008"], ("EXPECTED", "KD-3"))
        self.assertEqual(verdicts["0001|1002"], ("POTENTIAL_ISSUE", None))
        self.assertEqual(verdicts["0002|1007"], ("POTENTIAL_ISSUE", None))
        self.assertNotIn("0002|1006", verdicts)  # within tolerance -> match
        self.assertNotIn("0001|1004", verdicts)  # eco fee filtered out

        # LLM hand-off: batch contains only the two unexplained results, with evidence rows
        batch_path = project / "output" / "llm" / run_id / "batch_001.json"
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        ids = {r["record_key"]: r["result_id"] for r in batch["records"]}
        self.assertEqual(set(ids), {"0001|1002", "0002|1007"})
        self.assertIn("price_events_for_sku",
                      batch["records"][0]["evidence_data"])
        findings = {
            "run_id": run_id,
            "batch": 1,
            "findings": [
                {"result_id": ids["0001|1002"], "classification": "DATA_ISSUE", "kd_code": None, "confidence": 0.5,
                 "hypothesis": "Retail price manually overridden in cloud", "evidence": "x", "verification_steps": "y"},
                {"result_id": ids["0002|1007"], "classification": "INSUFFICIENT_EVIDENCE", "kd_code": None, "confidence": 0.1,
                 "hypothesis": "", "evidence": "", "verification_steps": ""},
            ],
        }
        (batch_path.parent /
         "findings_001.json").write_text(json.dumps(findings), encoding="utf-8")
        code, out = run_cli(project, "llm-import")
        self.assertEqual(code, 0, out)
        self.assertIn('"verdicts_updated": 1', out)
        self.assertIn('"left_unchanged_insufficient_evidence": 1', out)
        # re-export without --force must refuse because findings exist
        code, out = run_cli(project, "llm-export")
        self.assertEqual(code, 1)

        code, out = run_cli(project, "report")
        self.assertEqual(code, 0, out)
        workbook = project / "output" / "reports" / \
            f"price-compare-demo_parity_{run_id}.xlsx"
        import openpyxl

        wb = openpyxl.load_workbook(workbook)
        self.assertEqual(wb.sheetnames, ["Summary", "Classification_summary",
                         "Results", "Potential_issues", "Field_diffs", "KD_catalogue"])
        sheet = wb["Results"]
        header = [c.value for c in sheet[1]]
        col = {name: i for i, name in enumerate(header)}
        for row in sheet.iter_rows(min_row=2):
            if row[col["key.sku"]].value == "1002":
                self.assertEqual(
                    row[col["classification"]].value, "DATA_ISSUE")
                self.assertEqual(row[col["verdict_source"]].value, "llm")
                row[col["reviewed_classification"]].value = "POTENTIAL_ISSUE"
                row[col["review_notes"]].value = "Confirmed bug in price rounding"
            if row[col["key.sku"]].value == "1005":
                row[col["reviewed_classification"]].value = "EXPECTED"
                row[col["reviewed_kd_code"]].value = "KD-1"
        reviewed = project / "output" / "reports" / "reviewed.xlsx"
        wb.save(reviewed)
        code, out = run_cli(project, "review-import", "--file", str(reviewed))
        self.assertEqual(code, 0, out)
        feedback = json.loads((project / "output" / "feedback" /
                              f"{run_id}_review_feedback.json").read_text(encoding="utf-8"))
        self.assertEqual(
            (feedback["agreements"], feedback["disagreements"]), (1, 1))
        self.assertEqual(feedback["items"][0]["automated"]["source"], "llm")
        final_path = project / "output" / "reports" / \
            f"price-compare-demo_final_review_{run_id}.xlsx"
        self.assertTrue(final_path.exists())
        final_wb = openpyxl.load_workbook(final_path)
        self.assertEqual(final_wb.sheetnames[:5], [
                         "Summary", "Mismatches", "Missing_In_Source", "Missing_In_Target", "Duplicate_Keys"])
        final_headers = [cell.value for cell in final_wb["All_Results"][1]]
        for column in ("rule_verdict", "llm_verdict", "reviewed_classification", "review_notes"):
            self.assertIn(column, final_headers)
        self.assertEqual(self.verdicts(project, run_id, "manual")[
                         "0001|1002"], ("POTENTIAL_ISSUE", None))

    def test_load_is_idempotent_and_append_dedupes(self) -> None:
        project = self.generate(EXAMPLE_A, "mode_a_load")
        self.assertEqual(run_cli(project, "load")[0], 0)
        code, out = run_cli(project, "load")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count('"status": "SKIPPED"'), 3)
        # overlapping snapshot for an append dataset: only the new row is inserted
        events = project / "reference" / "price_events"
        (events / "price_events_20261102.csv").write_text(
            "store,sku,event_type,event_date\n1,1003,ADD,2026-11-01\n1,1009,ADD,2026-11-02\n", encoding="utf-8"
        )
        code, out = run_cli(project, "load", "--dataset", "price_events")
        self.assertEqual(code, 0, out)
        self.assertIn('"rows_inserted": 1', out)
        self.assertEqual(
            db_rows(project, "SELECT COUNT(*) FROM raw_price_events")[0][0], 3)
        # replace dataset: forced reload keeps exactly one copy
        code, out = run_cli(project, "load", "--dataset",
                            "legacy_prices", "--force")
        self.assertEqual(code, 0, out)
        self.assertEqual(
            db_rows(project, "SELECT COUNT(*) FROM raw_legacy_prices")[0][0], 8)

    def test_query_is_read_only(self) -> None:
        project = self.generate(EXAMPLE_A, "mode_a_query")
        run_cli(project, "init-db")
        self.assertEqual(
            run_cli(project, "query", "SELECT COUNT(*) FROM raw_legacy_prices")[0], 0)
        self.assertEqual(
            run_cli(project, "query", "DELETE FROM raw_legacy_prices")[0], 1)
        self.assertEqual(run_cli(
            project, "query", "WITH x AS (SELECT 1) DELETE FROM raw_legacy_prices")[0], 1)

    # -- Mode B -----------------------------------------------------------
    def test_mode_b_pairs_opposite_directions(self) -> None:
        project = self.generate(EXAMPLE_B, "mode_b")
        self.assertTrue((project / ".github" / "agents" /
                        "mismatch-report-demo-diff-ingestor.agent.md").exists())
        self.assertFalse((project / "config" / "comparison.json").exists())
        code, out = run_cli(project, "run")
        self.assertEqual(code, 0, out)
        run_id = self.latest_run(project)
        counts = dict(db_rows(
            project, "SELECT result_type, COUNT(*) FROM parity_result WHERE run_id = ? GROUP BY 1", (run_id,)))
        self.assertEqual(
            counts, {"MISMATCH": 1, "MISSING_IN_TARGET": 2, "MISSING_IN_SOURCE": 2})
        verdicts = self.verdicts(project, run_id)
        self.assertEqual(
            verdicts["10|2001|0|2026-11-10"], ("EXPECTED", "KD-1"))
        self.assertEqual(
            verdicts["12|2004|0|2026-11-10"], ("EXPECTED", "KD-5"))
        self.assertEqual(
            verdicts["12|2005|777|2026-11-10"], ("POTENTIAL_ISSUE", None))
        # test store filtered
        self.assertNotIn("99|2009|0|2026-11-10", verdicts)
        raw = db_rows(project, "SELECT COUNT(*) FROM raw_diff_src_only")[0][0]
        # heartbeat line without payload skipped by extract
        self.assertEqual(raw, 4)

    # -- Factory behaviour ------------------------------------------------
    def test_combined_project_supports_both_entry_workflows(self) -> None:
        mode_a = json.loads(EXAMPLE_A.read_text(encoding="utf-8"))
        mode_b = json.loads(EXAMPLE_B.read_text(encoding="utf-8"))
        combined = json.loads(json.dumps(mode_a))
        combined["project"]["name"] = "Combined Parity Demo"
        combined["project"]["slug"] = "combined-parity-demo"
        combined["project"]["mode"] = "AB"
        combined["datasets"].extend(mode_b["datasets"])
        combined["filters"].update(mode_b["filters"])
        combined["analysis_snapshots"] = mode_a["analysis_snapshots"] + \
            mode_b["analysis_snapshots"]
        combined["diff_ingest"] = mode_b["diff_ingest"]
        combined["samples"] = {
            **{name: str((EXAMPLE_A.parent / path).resolve()) for name, path in mode_a["samples"].items()},
            **{name: str((EXAMPLE_B.parent / path).resolve()) for name, path in mode_b["samples"].items()},
        }
        spec = self.tmp / "combined.spec.json"
        spec.write_text(json.dumps(combined), encoding="utf-8")
        project = self.generate(spec, "combined")
        agents = project / ".github" / "agents"
        self.assertTrue(
            (agents / "combined-parity-demo-comparator.agent.md").exists())
        self.assertTrue(
            (agents / "combined-parity-demo-diff-ingestor.agent.md").exists())

        code, out = run_cli(project, "run")
        self.assertEqual(code, 1)
        self.assertIn(
            "require --workflow compare or --workflow ingest-diff", out)
        code, compare_out = run_cli(project, "run", "--workflow", "compare")
        self.assertEqual(code, 0, compare_out)
        code, ingest_out = run_cli(project, "run", "--workflow", "ingest-diff")
        self.assertEqual(code, 0, ingest_out)
        code, analysis_out = run_cli(project, "run", "--from", "classify")
        self.assertEqual(code, 0, analysis_out)

    def test_force_regeneration_keeps_data_and_custom_rules(self) -> None:
        project = self.generate(EXAMPLE_A, "mode_a_regen")
        run_cli(project, "load")
        custom = project / "rules" / "custom_rules.py"
        custom.write_text(
            "def mine(record, db):\n    return False\n", encoding="utf-8")
        with self.assertRaises(new_project.SpecError):
            new_project.generate(EXAMPLE_A, project)
        result = new_project.generate(EXAMPLE_A, project, force=True)
        self.assertEqual(result["problems"], [])
        self.assertIn("def mine", custom.read_text(encoding="utf-8"))
        self.assertTrue(
            Path(result["backup"], "config", "datasets.json").exists())
        self.assertEqual(
            db_rows(project, "SELECT COUNT(*) FROM raw_legacy_prices")[0][0], 8)

    def test_spec_rejects_credentials_and_bad_slug(self) -> None:
        spec = json.loads(EXAMPLE_A.read_text(encoding="utf-8"))
        spec["project"]["slug"] = "Bad Slug"
        spec["datasets"][0]["connector"]["password"] = "x"
        problems = new_project.check_spec(spec)
        self.assertTrue(any("slug" in p for p in problems))
        self.assertTrue(any("credentials" in p for p in problems))

    def test_database_schema_and_snapshot_are_prechecked(self) -> None:
        project = self.generate(EXAMPLE_A, "mode_a_prerequisites")
        snapshot_config = project / "config" / "config.yaml"
        self.assertTrue(snapshot_config.exists())
        self.assertIn("price_events",
                      snapshot_config.read_text(encoding="utf-8"))

        code, out = run_cli(project, "precheck")
        self.assertEqual(code, 1)
        self.assertIn("database schema", out)
        self.assertEqual(run_cli(project, "init-db")[0], 0)
        self.assertEqual(run_cli(project, "precheck")[0], 0)

        for dataset in ("legacy_prices", "cloud_prices"):
            self.assertEqual(
                run_cli(project, "load", "--dataset", dataset)[0], 0)
            self.assertEqual(
                run_cli(project, "filter", "--dataset", dataset)[0], 0)
        self.assertEqual(run_cli(project, "compare")[0], 0)
        code, out = run_cli(project, "classify")
        self.assertEqual(code, 1)
        self.assertIn("Required analysis snapshot precheck failed", out)
        self.assertIn("price_events", out)

    def test_config_validation_reports_bad_references(self) -> None:
        project = self.generate(EXAMPLE_A, "mode_a_invalid")
        cmp_path = project / "config" / "comparison.json"
        cmp_cfg = json.loads(cmp_path.read_text(encoding="utf-8"))
        cmp_cfg["fields"][0]["target"] = "no_such_column"
        cmp_path.write_text(json.dumps(cmp_cfg), encoding="utf-8")
        code, out = run_cli(project, "precheck")
        self.assertEqual(code, 1)
        self.assertIn("no_such_column", out)


class UnitTest(unittest.TestCase):
    def test_normalize(self) -> None:
        self.assertEqual(
            normalize(" 2 ", {"type": "string", "zero_pad": 4}), "0002")
        self.assertEqual(normalize("8.00", {"type": "decimal"}), "8")
        self.assertEqual(
            normalize("01/11/2026", {"type": "date", "format": "%d/%m/%Y"}), "2026-11-01")
        self.assertEqual(normalize("abc", {"type": "decimal"}), "INVALID(abc)")
        self.assertIsNone(normalize("NULL", {"type": "string"}))
        self.assertTrue(values_equal(
            "4", "4.0004", {"type": "decimal", "tolerance": 0.001}))
        self.assertFalse(values_equal(
            "4", "4.01", {"type": "decimal", "tolerance": 0.001}))

    def test_conditions(self) -> None:
        record = {"result_type": "MISMATCH", "mismatch_fields": ["a"], "source": {"p": "0"}, "target": {
            "p": "2.5", "d": "2026-11-02"}, "details": {"d": {"source": "2026-11-01", "target": "2026-11-02"}}}
        self.assertTrue(
            evaluate({"field": "mismatch_fields", "op": "eq", "value": ["a"]}, record))
        self.assertTrue(
            evaluate({"field": "source.p", "op": "eq", "value": 0}, record))
        self.assertTrue(
            evaluate({"field": "target.p", "op": "gt", "value": 2}, record))
        self.assertTrue(evaluate({"field": "details.d.source", "op": "days_diff",
                        "field2": "details.d.target", "value": 1}, record))
        self.assertTrue(evaluate({"any": [{"field": "result_type", "op": "eq", "value": "X"}, {
                        "not": {"field": "source.missing", "op": "not_empty"}}]}, record))


if __name__ == "__main__":
    unittest.main()
