from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import run_pipeline


def initial_state() -> dict:
    return {
        "overall_status": "READY",
        "tasks": {
            "requirements-confirm": {"status": "SUCCESS"},
            **{
                task: {"status": "NOT_STARTED"}
                for task in run_pipeline.ORDER[1:]
            },
        },
    }


def test_task_retries_then_succeeds(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "task-state.json"
    state_path.write_text(json.dumps(initial_state()), encoding="utf-8")
    results = iter([
        SimpleNamespace(returncode=1, stdout="", stderr="transient failure"),
        SimpleNamespace(returncode=0, stdout="recovered", stderr=""),
    ])
    monkeypatch.setattr(run_pipeline, "STATE_PATH", state_path)
    monkeypatch.setattr(run_pipeline, "command_for",
                        lambda task, args: ["test-command"])
    monkeypatch.setattr(run_pipeline.subprocess, "run",
                        lambda *args, **kwargs: next(results))

    result = run_pipeline.run_task(
        "db-init", SimpleNamespace(max_retries=2))
    state = json.loads(state_path.read_text(encoding="utf-8"))

    assert result["status"] == "SUCCESS"
    assert result["attempts"] == 2
    assert state["tasks"]["db-init"]["status"] == "SUCCESS"
    assert state["tasks"]["db-init"]["human_inspection_required"] is False


def test_retry_exhaustion_requires_human_inspection(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "task-state.json"
    state_path.write_text(json.dumps(initial_state()), encoding="utf-8")
    monkeypatch.setattr(run_pipeline, "STATE_PATH", state_path)
    monkeypatch.setattr(run_pipeline, "command_for",
                        lambda task, args: ["test-command"])
    monkeypatch.setattr(
        run_pipeline.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="", stderr="persistent failure"),
    )

    result = run_pipeline.run_task(
        "db-init", SimpleNamespace(max_retries=1))
    state = json.loads(state_path.read_text(encoding="utf-8"))

    assert result["status"] == "HUMAN_INSPECTION_REQUIRED"
    assert result["attempts"] == 2
    assert result["human_inspection_required"] is True
    assert state["overall_status"] == "HUMAN_INSPECTION_REQUIRED"


def test_resume_continues_after_human_inspection_marker(monkeypatch, tmp_path: Path) -> None:
    state = initial_state()
    state["overall_status"] = "HUMAN_INSPECTION_REQUIRED"
    state["tasks"]["db-init"]["status"] = "HUMAN_INSPECTION_REQUIRED"
    state_path = tmp_path / "task-state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(run_pipeline, "STATE_PATH", state_path)
    calls = []
    monkeypatch.setattr(
        run_pipeline,
        "run_task",
        lambda task, args: calls.append(
            task) or {"task": task, "status": "SUCCESS"},
    )

    assert run_pipeline.main(["--mode", "resume"]) == 0
    assert calls == ["db-init"]
