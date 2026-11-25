# CPP - PM000003 Parity Analysis

Standalone PM000003 implementation for analysing directional CPP/CDCS pricing mismatches against deterministic reference evidence, optional LLM findings, and final human review.

This is a completed reference implementation inside `parity-project-factory/Standalone project/`. Its checked-in inputs, databases, reports, and presentations are synthetic demonstration artifacts. Production values and credentials are not included.

## Project Identity

- Project name: `CPP-PM000003-Parity-Analysis`
- Domain: pricing parity and mismatch analysis
- Entry workflow: Workflow B, supplied mismatch-report ingestion
- Analysis keys: store, snapshot day, product/offering, deal, price type, and effective date
- Requirements source: `docs/CONFIRMED_REQUIREMENTS.md`
- Project configuration: `config/cpp.yaml`
- Orchestrator: **CPP PM000003 Orchestrator**
- Rule precedence: `manual review > LLM finding > deterministic verdict`

## Confirmed Scope

The implementation must not infer missing contracts. If a run-specific source, snapshot mapping, database path, classification rule, or acceptance condition is missing, the affected task returns `BLOCKED` until it is confirmed.

## Architecture

The controlled flow is:

```text
Five CPP snapshots + IMS snapshots + two directional mismatch CSVs
    -> canonical SQLite database
    -> CPP packet explosion and evidence lookup
    -> deterministic KD classification
    -> controlled LLM candidate exchange
    -> manual confirmation/review
    -> reconciled Excel reports and presentations
```

## Inputs

| Input | Files | Purpose |
|---|---|---|
| CPP packet snapshot | `cpp_data/corpPricePackets.csv` | Rebuild CPP packet evidence |
| Deal master | `cpp_data/dealPriceMaster.csv` | Deal validation and evidence |
| Regular master | `cpp_data/regularPriceMaster.csv` | Regular-price evidence |
| Zone/store relation | `cpp_data/zoneStoreRelation.csv` | Store-to-zone coverage |
| Staging price snapshot | `cpp_data/stagingProductPrice.csv` | Staging comparison evidence |
| IMS source database | `ims_data/ims_source.db` | Per-store snapshot tables |
| IMS day map | `ims_data/day-map.json` | Explicit source-table, store, and day mapping |
| CDCS-only mismatches | `input/Diff-mismatch-CDCS-missing-in-CPP.csv` | Directional mismatch input |
| CPP-only mismatches | `input/Diff-mismatch-CPP-missing-in-CDCS.csv` | Reverse mismatch input |

The checked-in example contains stores `5101`-`5505`, products beginning with `7001`, snapshot dates `2026-11-16` through `2026-11-20`, `250` normalized mismatch rows, and `250` verdict rows.

## Configuration And Rules

- `config/pipeline.yaml`: ordered tasks, agents, prerequisites, and outputs
- `config/cpp.yaml`: confirmed project identity and behavior
- `config/generated-run.json`: parser and generated-run contract
- `config/synthetic-run.json`: retained generation configuration
- `ims_data/day-map.json`: explicit store/snapshot-table/day mapping
- `docs/KD_RULES.md`: ordered deterministic KD behavior
- `docs/CONFIRMED_REQUIREMENTS.md`: requirements gate
- `docs/REQUIREMENTS_TRACEABILITY.md`: requirement-to-implementation mapping

`KD-2`, `KD-8`, `KD-9`, and `KD-10` remain `EXPECTED`. Missing proof is represented through confirmation fields instead of weakening the deterministic verdict.

## Canonical Database

- Database: `pm000003_mf_packets_multi_store.db`
- Schema: `schema/001_create_core_schema.sql` and `schema/002_create_mf_template.sql`
- Core tables: `_metadata`, `cpp_price_packets`, `deal_price_master`, `regular_price_master`, `zone_store_relation`, `staging_product_price`, `mismatch_input`, `mismatch_verdict`, and `cpp_data`
- Store tables use the `mf_data_` prefix plus the four-digit store, for example `mf_data_5101`
- Validation: schema version, table set, required indexes, row reconciliation, and evidence gates

## Agents

| Agent | Responsibility |
|---|---|
| CPP PM000003 Orchestrator | Coordinates the requirements gate, task dependencies, resume, and status |
| CPP Requirements Analyst | Confirms requirements and maintains the accepted contract |
| CPP Database Migrator | Initializes and validates the canonical database |
| CPP CPP Loader | Loads and validates five CPP snapshot files |
| CPP IMS Migrator | Maps, loads, and reconciles IMS store/day snapshots |
| CPP Report Runner | Parses directional mismatch CSVs and persists normalized rows |
| CPP CPP Analyst | Explodes packet JSON and rebuilds `cpp_data` |
| CPP Classifier | Applies ordered deterministic KD rules and evidence gates |
| CPP LLM Analyst | Exchanges validated unresolved candidates and findings |
| CPP Review Coordinator | Imports reviewed manual decisions |
| CPP Reporter | Builds the final workbook |
| CPP Validator | Independently validates database and report reconciliation |
| CPP Consolidated Reporter | Combines explicitly approved reports |

Agent definitions are under `.github/agents/` with project instructions under `.github/instructions/`.

## Pipeline Tasks

The exact order in `config/pipeline.yaml` is:

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

The task driver supports full, resume, status, and independent task execution. A failed task is retried at most twice by default (`execution_policy.max_retries`). After retry exhaustion, the state becomes `HUMAN_INSPECTION_REQUIRED` as an audit label: it records that human inspection is recommended while preserving the task failure and all attempts. Automatic resume continues and reruns the task; it does not wait for approval. Use `--max-retries` only as an explicit run override.

```powershell
python scripts/run_pipeline.py --mode status
python scripts/run_pipeline.py --mode task --task db-init --db pm000003_mf_packets_multi_store.db
python scripts/run_pipeline.py --mode resume `
  --db pm000003_mf_packets_multi_store.db `
  --cpp-dir cpp_data `
  --ims-source ims_data/ims_source.db `
  --day-map ims_data/day-map.json `
  --config config/generated-run.json
```

A task starts only when its declared prerequisite evidence is present. The driver stores each attempt and its output in ignored `state/task-state.json`.

When the LLM returns `INSUFFICIENT_EVIDENCE`, the deterministic verdict is unchanged, but the row receives `HUMAN_APPROVAL_REQUIRED` in the final report audit columns. Review columns capture a reviewed classification, notes, reviewer identity, and timestamp when provided. This status does not block the pipeline, automatic resume, or final workbook generation.

## Recreate The Synthetic Run

Install dependencies and recreate the complete demonstration dataset, database, outputs, and analysis workbook:

```powershell
python -m pip install -r requirements.txt
python scripts/generate_run.py
```

The generator replaces the active synthetic inputs, canonical database, and non-presentation reports. Backups are written outside the repository.

## Validation

Run all automated checks from this folder:

```powershell
python -m pytest -q
python scripts/validate_database.py --db pm000003_mf_packets_multi_store.db
python scripts/validate_outputs.py `
  --db pm000003_mf_packets_multi_store.db `
  --workbook reports/pm000003_analysis.xlsx
```

Expected demonstration reconciliation is `250` mismatch rows, `250` verdict rows, `250` workbook result rows, and no malformed parsed rows.

## Outputs

| Output | Purpose |
|---|---|
| `pm000003_mf_packets_multi_store.db` | Canonical inputs, evidence, verdicts, and review state |
| `reports/pm000003_analysis.xlsx` | Main analysis and review workbook |
| `reports/pm000003_analysis_YYYY-MM-DD.xlsx` | Daily working workbooks |
| `output/llm_candidates.json` | Controlled unresolved candidates |
| `output/llm_findings.json` | Validated LLM findings |
| `reports/RUN_SUMMARY.md` | Run-level metrics and method summary |
| `reports/production_metrics.json` | Metrics consumed by the production deck |
| `reports/run_metrics.json` | Generated run metrics |
| `reports/CPP_Parity_AI_Factory_Demo.pptx` | 21-slide business and AI-factory demonstration |
| `reports/CPP_PM000003_Production_Metrics.pptx` | 8-slide production-metrics presentation |

Regenerate presentations independently:

```powershell
python scripts/generate_demo_deck.py
python scripts/generate_production_metrics_deck.py
```

## CI/CD

Repository-root workflows are:

- `.github/workflows/ci.yml`: factory tests, CPP tests, compilation, schema creation, and validation evidence
- `.github/workflows/parity-operations.yml`: scheduled validation and approved self-hosted full runs

Both workflows use this nested working directory:

`parity-project-factory/Standalone project/CPP-PM000003-Parity-Analysis`

## Data And Security Policy

- All checked-in CPP project datasets in this repository are synthetic demonstration data.
- No production credentials, API keys, connection strings, or environment files are tracked.
- Runtime state, locks, WAL files, database backups, and logs remain excluded unless explicitly approved.
- A similar project must document its own data classification; do not assume synthetic data may be copied into a production implementation.

## Reuse For A Similar Project

Use the pattern in this project, not its business values:

1. Copy the parent [README template](../README_TEMPLATE.md) into the new standalone project as `README.md`.
2. Confirm workflow mode, systems, owners, keys, dates, fields, snapshots, rule precedence, and output contract.
3. Reuse the orchestrator plus specialist-agent structure and the resumable task model.
4. Replace CPP/CDCS datasets, parser regexes, day mappings, schema fields, and KD logic with confirmed equivalents.
5. Update CI working directories and artifact paths at the repository root.
6. Generate synthetic fixtures and tests before adding any production-like data.
7. Reconcile database, workbook, report, and presentation metrics.
8. Add the completed project to [the standalone project index](../README.md).

Do not copy synthetic stores, products, prices, dates, KD values, or classification totals as though they were business requirements for the next project.

## Definition Of Done

- Confirmed requirements are traceable to config, schema, scripts, rules, and tests.
- All input contracts and explicit snapshot mappings are present.
- Deterministic and human-review precedence is implemented and documented.
- Full-run and independently resumed task paths are validated.
- Database, verdict, and workbook counts reconcile.
- PPTX and XLSX reports are regenerated from the current run.
- Secret, ignored-runtime, and stale-run scans pass.
- Root CI workflows execute from the nested standalone-project path.
