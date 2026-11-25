from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def load_cost_usage():
    path = ROOT / "cost_usage.py"
    spec = importlib.util.spec_from_file_location("cost_usage", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_usage_summary_marks_missing_otel_as_unavailable(tmp_path: Path) -> None:
    cost_usage = load_cost_usage()

    summary = cost_usage.usage_summary([], [], str(tmp_path))

    assert summary["capture_status"] == "unavailable"
    assert summary["requests"] == 0
    assert summary["computed_cost"] is None
    assert summary["logged_cost"] is None
    assert summary["in_pipeline_model_requests"] == 0
    assert summary["in_pipeline_ai_cost"] == 0.0


def test_cost_file_contains_measurable_request_summary() -> None:
    cost_usage = load_cost_usage()
    rows = [{
        "input_tokens": 100,
        "cached_tokens": 20,
        "output_tokens": 10,
        "duration_ms": 250,
        "cost": 0.0012,
        "logged_cost": 0.0013,
    }]

    summary = cost_usage.usage_summary(rows, [], "/example/logs")

    assert summary["capture_status"] == "measured"
    assert summary["input_tokens"] == 100
    assert summary["cached_tokens"] == 20
    assert summary["output_tokens"] == 10
    assert summary["duration_ms"] == 250
    assert summary["computed_cost"] == 0.0012
    assert summary["logged_cost"] == 0.0013
    json.dumps(summary)
