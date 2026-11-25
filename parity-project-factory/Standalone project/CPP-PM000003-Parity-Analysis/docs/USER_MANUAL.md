# User Manual

## Setup

```powershell
python -m pip install -r requirements.txt
python scripts/init_database.py --db output/pm000003.db
python scripts/validate_database.py --db output/pm000003.db
```

Runtime data remains local under `input/`, `cpp_data/`, `ims_data/`, `reports/`, and `output/`. Never commit production data or credentials.

## Independent Pipeline Tasks

Use one task at a time:

```powershell
python scripts/run_pipeline.py --mode task --task db-init --db output/pm000003.db
python scripts/run_pipeline.py --mode task --task cpp-load --db output/pm000003.db --cpp-dir cpp_data
python scripts/run_pipeline.py --mode task --task ims-migrate --db output/pm000003.db --ims-source ims_data/source.db --day-map ims_data/day-map.json
python scripts/run_pipeline.py --mode task --task report-parse --db output/pm000003.db --config config.json
```

Use `--mode status` to inspect state, `--mode resume` for the next unresolved task, or `--mode full` for dependency-ordered execution. Every IMS import requires an explicit table-to-ISO-day map.

## Analysis and Reporting

```powershell
python scripts/run_pipeline.py --mode task --task cpp-explode --db output/pm000003.db
python scripts/run_pipeline.py --mode task --task classify --db output/pm000003.db --analysis-date YYYY-MM-DD
python scripts/run_pipeline.py --mode task --task llm-review --db output/pm000003.db --llm-candidates output/llm_candidates.json
python scripts/review_and_report.py report --db output/pm000003.db --output reports/review.xlsx
python scripts/review_and_report.py review-import --db output/pm000003.db --file reports/reviewed.xlsx --final-output reports/final.xlsx
python scripts/validate_outputs.py --db output/pm000003.db --workbook reports/final.xlsx
```

Manual review is performed in `All_Results`. Final output contains Summary, Summary_detail, All_Results, and directional sheets.

## Optional Consolidation

```powershell
python scripts/consolidated_report.py --report reports/final.xlsx --output reports/consolidated.xlsx
```

Consolidation accepts only explicitly named reports.

## Common Failures

- Missing source/day mapping: provide `--day-map`; ambiguous dates are never inferred.
- CSV column error: re-export all columns declared in `scripts/cpp_datasets.py`.
- Missing snapshot: load the required CPP/IMS evidence before classification.
- LLM insufficient evidence: deterministic verdict remains unchanged, the row is marked `HUMAN_APPROVAL_REQUIRED`, and final reporting is blocked until manual review is imported.
- Task failures: the pipeline retries each failed task at most twice by default. Retry exhaustion changes the state to `HUMAN_INSPECTION_REQUIRED`; automatic resume stops until a human inspects the evidence and explicitly reruns the task.
- Workbook validation mismatch: reconcile DB `mismatch_input`/`mismatch_verdict` with `All_Results`.
