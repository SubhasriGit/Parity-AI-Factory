# Pipeline Execution Model

## Task Contract

Every task in `config/pipeline.yaml` has:

- a stable task ID;
- one owning agent;
- declared prerequisites;
- expected outputs;
- an execution status in `state/task-state.json`.

Tasks do not implicitly rerun earlier tasks.

## Supported Invocation Modes

### Full Pipeline

The orchestrator validates requirements, initializes the database, loads snapshots, parses the report, classifies, performs optional LLM review, imports human review, generates the final report, validates, and optionally consolidates.

### Independent Task

Example: `Run task cpp-load independently.`

The orchestrator checks only `cpp-load` prerequisites: confirmed requirements and valid database evidence. If the evidence exists, it invokes the CPP loader without rerunning `requirements-confirm` or `db-init` work that is already complete.

### Run From the Middle

Example: `Run from task classify for run <id>.`

The orchestrator verifies that report parsing, CPP loading, IMS migration, and packet explosion have successful evidence for that run. It then starts at `classify` and continues only when requested.

### Resume

The orchestrator reads `state/task-state.json`, finds the first unresolved task, verifies its prerequisites and inputs, and resumes there. It does not rebuild the pipeline state from assumptions.

### Status Only

The orchestrator reads configuration, task evidence, and open clarifications. It does not execute data-processing commands.

## Task State

Allowed states:

- `NOT_STARTED`
- `READY`
- `RUNNING`
- `SUCCESS`
- `PARTIAL`
- `FAILED`
- `BLOCKED`

A task may claim `SUCCESS` only when its required output evidence is present and validated. A task becomes `BLOCKED` when a confirmed input, mapping, schema, or P0 requirement is missing.

## Independent Execution Preconditions

A worker may run independently when all of the following are true:

1. The user named a valid task ID.
2. Required inputs are explicit and available.
3. Every declared prerequisite has current successful evidence or an explicitly supplied equivalent.
4. The task does not depend on an unresolved P0 requirement.
5. The owning agent has validated its preconditions.

Otherwise, return `BLOCKED` and list the exact missing evidence.

## Evidence Contract

Task evidence should include, as applicable:

- exact commands run;
- input and output paths;
- database path and backup path;
- schema/table/index counts;
- parsed, inserted, ignored, skipped, and total rows;
- run/day/store identifiers;
- result and verdict counts;
- workbook sheet names and reconciliation results;
- validation/test pass-fail summary;
- clarification IDs that remain open.
