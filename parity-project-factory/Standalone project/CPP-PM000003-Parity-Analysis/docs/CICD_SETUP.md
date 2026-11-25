# Basic CI/CD and Scheduling Setup

## Included Workflows

### `.github/workflows/ci.yml`

Runs for pull requests and pushes to `main` or `master`:

1. checkout;
2. Python setup and dependency installation;
3. compile validation;
4. complete pytest suite;
5. fresh database creation and schema validation;
6. test/database evidence upload.

### `.github/workflows/parity-operations.yml`

Runs in two modes:

- **Scheduled or validate-only:** GitHub-hosted runner executes tests, Python compilation, and fresh database validation. It never reads production data.
- **Manual full-run:** self-hosted runner executes the approved data workflow and uploads the review workbook, LLM candidate file, and run evidence. Final publication remains behind the human-review gate.

## Self-Hosted Runner Requirement

A full production/scheduled data run needs a runner that can safely access the approved CPP, IMS, and mismatch inputs. Configure the runner environment and place inputs only in approved local or mounted folders.

Do not commit production CSV, database, workbook, or credential files.

## GitHub Environment

Create an environment named `parity-production` and configure:

- required reviewers for manual full runs;
- self-hosted runner availability;
- branch/environment protection;
- approved deployment windows;
- retention and access policy for workflow artifacts.

## Manual Full-Run Inputs

The workflow accepts:

- database path;
- CPP CSV directory;
- mismatch configuration path;
- output workbook path;
- optional IMS source database;
- optional explicit day-map JSON;
- optional analysis date.

The five CPP files must be present in the CPP directory. IMS source and day map must be supplied together.

## Secrets and Connectors

The current workflow requires local/mounted files and no production credential. When SQL, FTP/SFTP, blob, or cloud connectors are added, store credentials in GitHub Environment secrets or an approved secret manager. Never store them in workflow YAML, config JSON, logs, or artifacts.

## Retry And Human Review Boundary

Each failed task receives at most the configured `execution_policy.max_retries` retries (default: two). Exhaustion is recorded as `HUMAN_INSPECTION_REQUIRED` for audit and later investigation. Automatic resume continues and reruns the failed task; this status is not an approval gate.

Automation produces the working and final reports with the current evidence. Rows where the LLM returns `INSUFFICIENT_EVIDENCE` remain visible as `HUMAN_APPROVAL_REQUIRED`; optional review fields can record classification, notes, reviewer identity, and timestamp. Human review does not block execution or final report generation.

## Recommended Branch Rules

Require successful `CPP CI / validate` before merge. Require at least one reviewer. Restrict changes to `.github/workflows/`, schema, config, and rule logic to the project maintainers.
