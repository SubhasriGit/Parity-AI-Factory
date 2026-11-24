# <PROJECT_NAME> - <SYSTEM_OR_DOMAIN>

## Purpose

Describe the business problem, systems involved, expected decision, and why this standalone parity project exists.

## Project Identity

- Project name: `<PROJECT_NAME>`
- Domain: `<DOMAIN>`
- Workflow: `<A | B | AB>`
- Primary data key: `<KEYS>`
- Analysis granularity: `<STORE / PRODUCT / DEAL / DATE OR OTHER>`
- Requirements source: `<REQUIREMENTS_FILE>`
- Owner: `<OWNER_OR_TEAM>`

## Confirmed Scope

List only confirmed requirements. Do not infer missing contracts.

- Input systems and extraction owners: `<DETAILS>`
- Source and target/reference datasets: `<DETAILS>`
- Comparison or mismatch rules: `<DETAILS>`
- Known discrepancy rules: `<DETAILS>`
- Human-review requirements: `<DETAILS>`
- Acceptance criteria: `<DETAILS>`

If a requirement is not confirmed, record it in the clarification register and stop the affected task rather than applying a default.

## Entry Point

Open this standalone project folder in VS Code and select `<ORCHESTRATOR_AGENT>`.

Useful requests:

- `Design and confirm the project requirements.`
- `Run the full pipeline.`
- `Run task <TASK_NAME> independently.`
- `Resume from the last completed task.`
- `Show blocked prerequisites and task status.`

## Architecture

Describe the controlled data flow:

```text
Inputs -> validation -> staging/database -> comparison or mismatch ingestion
      -> deterministic classification -> optional LLM review -> human review
      -> final reports -> output reconciliation
```

Record the implementation-specific components:

- Input connectors: `<LOCAL FILE / SQL / FTP / CLOUD>`
- Canonical database: `<DATABASE_PATH_AND_SCHEMA>`
- Required tables: `<TABLE_NAMES>`
- Snapshot-day strategy: `<STRATEGY>`
- Rule precedence: `manual review > LLM finding > deterministic verdict`

## Inputs

Document every required input.

| Input | Source | Format | Required fields | Snapshot rule | Example location |
|---|---|---|---|---|---|
| `<NAME>` | `<SYSTEM>` | `<CSV / JSON / XLSX / DB>` | `<FIELDS>` | `<RULE>` | `<PATH>` |

## Configuration

- Pipeline/task order: `<CONFIG_PATH>`
- Project identity and requirements: `<CONFIG_PATH>`
- Dataset registry: `<CONFIG_PATH>`
- Mappings: `<CONFIG_PATH>`
- Filters: `<CONFIG_PATH>`
- Known discrepancies: `<CONFIG_PATH>`
- LLM configuration: `<CONFIG_PATH>`

## Pipeline Tasks

List ordered and independently runnable tasks.

1. `<TASK_ID>` - `<PURPOSE>`; prerequisites: `<PREREQUISITES>`; output: `<OUTPUT>`
2. `<TASK_ID>` - `<PURPOSE>`; prerequisites: `<PREREQUISITES>`; output: `<OUTPUT>`

A task may run independently only after its declared prerequisites and evidence are present.

## Agents and Responsibilities

List the orchestrator and specialists.

| Agent | Responsibility | Primary files or commands |
|---|---|---|
| `<AGENT>` | `<RESPONSIBILITY>` | `<PATHS>` |

## Commands

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Initialize and validate the database:

```powershell
python scripts/<INIT_SCRIPT> --db <DATABASE>
python scripts/<VALIDATION_SCRIPT> --db <DATABASE>
```

Run the complete pipeline:

```powershell
python scripts/<PIPELINE_SCRIPT> full
```

Run, resume, or inspect one task:

```powershell
python scripts/<PIPELINE_SCRIPT> task <TASK_ID>
python scripts/<PIPELINE_SCRIPT> resume
python scripts/<PIPELINE_SCRIPT> status
```

Replace generic placeholders with exact project commands before completion.

## Outputs

| Output | Purpose | Generated path |
|---|---|---|
| Canonical database | Persisted inputs, evidence, verdicts, and review data | `<PATH>` |
| Analysis workbook | Human-reviewable final result | `<PATH>` |
| LLM candidates/findings | Controlled AI review exchange | `<PATHS>` |
| Summary/report | Management or business summary | `<PATH>` |
| Presentation | Demo or executive presentation | `<PATH>` |

## Validation

Run the exact project checks:

```powershell
python -m pytest -q
python scripts/<OUTPUT_VALIDATOR> --db <DATABASE> --workbook <WORKBOOK>
```

Record validation expectations such as row reconciliation, malformed rows, schema version, required indexes, classification totals, and evidence gates.

## Data and Security Policy

- Commit production data only when the project owner explicitly approves it.
- Prefer synthetic fixtures for examples, tests, demos, and this repository by default.
- Never commit passwords, tokens, API keys, connection strings, private keys, or environment files.
- Keep backups, transient state, locks, and local logs out of the tracked project unless specifically approved.
- State clearly whether each checked-in dataset is synthetic, anonymized, or production-approved.

## Reuse Guide

To reuse this design for a similar project:

1. Copy this template to the new standalone project as `README.md`.
2. Replace all angle-bracket placeholders with confirmed values.
3. Copy the factory-generated project into `parity-project-factory/Standalone project/<PROJECT_FOLDER>/`.
4. Confirm workflow mode, inputs, keys, rules, reports, and manual-review ownership.
5. Update the project-specific agents, config, schema, scripts, tests, and CI paths together.
6. Run factory tests and standalone-project tests.
7. Verify reports, database rows, and checked-in data satisfy the declared data policy.
8. Add the new project to the parent `Standalone project/README.md` index.

## Definition of Done

- Requirements and accepted assumptions are documented.
- Exact input contracts and output locations are stated.
- Schema, rules, agents, scripts, and tests agree with the README.
- Full and independent task execution are validated.
- Reports reconcile with the canonical database.
- No secrets or unapproved data are present in Git.
- CI paths work from the repository root.
