# pyright: reportMissingImports=false
from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from init_database import initialize_database
from llm_bridge import BUILTIN_GUARDRAILS, calculate_cost, export_candidates, load_guardrails


def seed(db: Path, count: int) -> None:
    initialize_database(db)
    connection = sqlite3.connect(str(db))
    for index in range(count):
        cursor = connection.execute(
            "INSERT INTO mismatch_input(day,direction,store,offering_number,deal_number,price_type,effective_date,dealer_cost_price,retail_price,casting_price,timestamp_utc,message_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ["2026-08-14", "CDCS_missing_in_CPP", "0035", f"{index + 1:07d}", "7101", "PROMO",
             "2026-08-14", "0.500", "1.000", "0.000", "2026-08-14 10:00:00", f"m{index}"])
        connection.execute(
            "INSERT INTO mismatch_verdict VALUES (?,?,?,?,?,?,?)",
            [cursor.lastrowid, "POTENTIAL_ISSUE", "KD-2?", 0.45, f"store 0035 deal 7101 offering {index + 1:07d}",
             json.dumps({"store": "0035"}), json.dumps(["priceChangeEvent"])])
    connection.commit()
    connection.close()


def guardrails(**overrides) -> dict:
    config = copy.deepcopy(BUILTIN_GUARDRAILS)
    config["pricing"].update(
        {"input_per_million": 2.0, "cached_per_million": 1.0, "output_per_million": 8.0})
    config.update(overrides)
    return config


def test_calculate_cost_formula() -> None:
    pricing = {"input_per_million": 2.0,
               "cached_per_million": 1.0, "output_per_million": 8.0}
    assert calculate_cost(pricing, 1_000_000, 500_000,
                          cached_tokens=200_000) == pytest.approx(1.6 + 0.2 + 4.0)


def test_redaction_hides_identifiers_everywhere(tmp_path: Path) -> None:
    db = tmp_path / "a.db"
    seed(db, 2)
    out = tmp_path / "c.json"
    export_candidates(db, out, guardrails=guardrails())
    text = out.read_text(encoding="utf-8")
    assert "0035" not in text and "7101" not in text and "0000001" not in text
    assert json.loads(text)["records"][0]["store"].startswith("h_")


def test_redaction_can_be_required_to_use_a_salt(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "a.db"
    seed(db, 1)
    config = guardrails()
    config["redaction"]["require_salt"] = True
    monkeypatch.delenv(config["redaction"]["salt_env"], raising=False)
    with pytest.raises(ValueError):
        export_candidates(db, tmp_path / "c.json", guardrails=config)
    monkeypatch.setenv(config["redaction"]["salt_env"], "secret")
    assert export_candidates(db, tmp_path / "c.json",
                             guardrails=config)["candidates"] == 1


def test_candidate_and_batch_caps(tmp_path: Path) -> None:
    db = tmp_path / "a.db"
    seed(db, 5)
    result = export_candidates(
        db, tmp_path / "c.json", guardrails=guardrails(max_rows_per_batch=2, max_batches=2))
    assert (result["candidates"], result["skipped_by_limit"],
            result["batches"]) == (4, 1, 2)
    batches = [record["batch"] for record in json.loads(
        (tmp_path / "c.json").read_text())["records"]]
    assert batches == [1, 1, 2, 2]


def test_spend_ceiling_truncates_and_writes_estimate(tmp_path: Path) -> None:
    db = tmp_path / "a.db"
    seed(db, 10)
    unlimited = export_candidates(
        db, tmp_path / "u.json", guardrails=guardrails())
    capped = export_candidates(db, tmp_path / "c.json",
                               guardrails=guardrails(max_estimated_cost_per_run=unlimited["estimated_cost"] / 2))
    assert 0 < capped["candidates"] < 10
    assert capped["skipped_by_budget"] == 10 - capped["candidates"]
    assert capped["estimated_cost"] <= unlimited["estimated_cost"] / 2
    estimate = json.loads(Path(capped["estimate"]).read_text(encoding="utf-8"))
    assert estimate["basis"] == "estimate_not_billed" and estimate["candidates_eligible"] == 10


def test_missing_guardrail_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_guardrails(tmp_path / "missing.json")
