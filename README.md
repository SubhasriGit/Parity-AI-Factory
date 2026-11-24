# Project1 - PM000003 Parity Analysis

This folder is the standalone PM000003 mismatch-analysis project governed by `docs/CONFIRMED_REQUIREMENTS.md`.

The implementation is intentionally not inferred. The project follows a requirements-confirmation gate before scripts, schema, reports, or business rules are implemented.

## Current Status

- Project structure: created
- Requirements source: uploaded PM000003 recreation brief plus inspected reference implementation
- Phase 1 implementation: canonical schema, dataset registry, database initializer, and validator complete
- Orchestrator: scaffolded
- Independent sub-agents: scaffolded
- Requirements gate: confirmed; run-specific input checks remain mandatory

## Golden Rules

1. Do not assume missing input contracts, file names, database paths, business rules, snapshot-day mappings, or acceptance behavior.
2. Ask focused clarification questions and record the confirmed answer before implementation.
3. The orchestrator may run the complete pipeline or any named task independently.
4. Every task validates only the prerequisites it owns and uses explicit task outputs.
5. If a prerequisite is missing or ambiguous, stop that task and return `BLOCKED`; do not silently continue from defaults.
6. Keep production exports, credentials, and populated databases outside Git.
7. Deterministic code and tests own processing behavior; agents coordinate only.
8. Use the precedence `manual review > LLM finding > deterministic verdict` for reporting.
9. Human review creates the final published workbook; automated reports remain working outputs.
10. Use synthetic fixtures for implementation tests.

## Project Entry Point

Open this folder in VS Code and select **Project1 PM000003 Orchestrator**.

Examples:

- `Design and confirm the project requirements.`
- `Run task db-init independently.`
- `Run from task cpp-load using the latest confirmed prerequisites.`
- `Run report-parse independently for the named input file.`
- `Show blocked requirements and task status.`

## Pipeline Tasks

The ordered pipeline is defined in `config/pipeline.yaml`:

1. `requirements-confirm`
2. `db-init`
3. `cpp-load`
4. `ims-migrate`
5. `report-parse`
6. `cpp-explode`
7. `classify`
8. `llm-review`
9. `human-review-import`
10. `final-report`
11. `validate`
12. `consolidate`

A caller may execute a task independently when its declared prerequisites are satisfied. Task execution does not require rerunning earlier successful tasks.

## CI/CD and Scheduling

The project includes `.github/workflows/ci.yml` for pull-request/push validation and `.github/workflows/parity-operations.yml` for scheduled safety validation plus approved manual full runs on a self-hosted runner. See `docs/CICD_SETUP.md` for environment, secrets, inputs, artifact, and human-review setup.

## Demo Presentation

Generate or refresh the business and AI-factory demo deck with:

```powershell
python scripts/generate_demo_deck.py
```

The output is `reports/Project1_Parity_AI_Factory_Demo.pptx`. It separates observed run metrics from illustrative productivity estimates and documents telemetry as a future measurement layer.

## Folder Guide

- `.github/agents/`: orchestrator and independently runnable specialist agents
- `.github/instructions/`: project-wide implementation rules
- `config/`: pipeline, application, and snapshot contracts
- `docs/`: requirements, clarification register, design, and future manuals
- `schema/`: future executable SQLite schema
- `scripts/`: future task implementations
- `tests/fixtures/`: synthetic test data only
- `state/`: local task status and evidence records, ignored by Git
- `input/`, `cpp_data/`, `ims_data/`, `reports/`, `output/`: local runtime locations, ignored by Git

## Next Gate

Use `docs/CONFIRMED_REQUIREMENTS.md` and `config/project1.yaml` as the current requirements source, then provide task-specific files and mappings when running the pipeline.
