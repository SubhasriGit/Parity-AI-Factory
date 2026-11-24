# Parity Project Factory

A template factory that **creates new parity projects** — each in its own folder or repository — with the folders, configuration, rules, agents (orchestrator and workers), skills, docs and a tested pipeline engine needed for that project's requirements.

- **Workflow A**: compare source and target files, then analyse the differences.
- **Workflow B**: analyse a difference report produced by another tool (like PM000003).
- **Mode `AB`**: keep both workflows in the same generated project and select one for each run. Do not create separate A and B project folders for the same parity solution.

Detailed overview: [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md). Design rationale: [docs/DESIGN.md](docs/DESIGN.md). Spec fields: [docs/SPEC_REFERENCE.md](docs/SPEC_REFERENCE.md).

## Factory versus runnable projects

Keep generated projects outside this factory. The sibling layout used for the runnable examples is:

```text
Parity Pipeline\
  parity-project-factory\      Build and maintain the generator here
  parity-projects\
    price-compare-demo\        Standalone Mode A example with sample data
    mismatch-report-demo\      Standalone Mode B example with sample data
```

| What you want to do | Folder to open in VS Code | Agent to select |
|---|---|---|
| Design a new project or maintain the factory | `parity-project-factory` | Parity Project Designer |
| Compare the sample source and target prices | `parity-projects\price-compare-demo` | Price Compare Demo Orchestrator |
| Analyse the sample mismatch reports | `parity-projects\mismatch-report-demo` | Mismatch Report Demo Orchestrator |

The two demo folders are separate examples of supported starting workflows. A real project that needs both starting points should be generated once with mode `AB`, not as two project folders.

Open one project folder at a time to keep its Copilot agents and instructions separate.
Each generated project owns its `.github/`, `config/`, `rules/`, data and reports.
The factory's `.github/` contains only factory customizations; `templates/project/`
contains reusable blueprints, not an active project's agents or configuration.
Keep those templates and the example specs/sample fixtures in the factory.
The sibling projects are generated separately; they are not included in the factory.

## How to create a project

### With Copilot (recommended)
1. Open this folder in VS Code.
2. In Copilot Chat select the **Parity Project Designer** agent and describe your parity: the systems, how you get the files, and what counts as a match.
3. The designer asks questions section by section (identity → mode → datasets → filters → keys or diff interpretation → known discrepancies → LLM scope → reports), confirms each one, saves `specs/<slug>.spec.json`, generates the project and runs a precheck.

### From the command line
```
python -m pip install -r requirements.txt
python factory/inspect_sample.py --file <your sample file>            # draft a column mapping
python factory/new_project.py --spec specs/<slug>.spec.json --validate-only
python factory/new_project.py --spec specs/<slug>.spec.json --dest C:/work/<slug> [--with-samples] [--git-init]
```

For a generated mode `AB` project, start a full run explicitly with `python scripts/parity.py run --workflow compare` or `python scripts/parity.py run --workflow ingest-diff`.

Try the examples:
```
python factory/new_project.py --spec examples/mode-a-price-compare/spec.json --dest C:/work/price-compare-demo --with-samples
cd C:/work/price-compare-demo
python scripts/parity.py run
```

## What a generated project contains

```
<project>/
  .github/agents/        <Project> Orchestrator + Setup, Loader, Filter, Comparator|Diff Ingestor, Classifier, LLM Analyst, Reporter
  .github/skills/        add-dataset, define-known-discrepancy, tune-from-review, investigate-result
  .github/prompts/       run-parity
  .github/instructions/  config editing rules;  .github/copilot-instructions.md  project rules
  config/                project.json, datasets.json, mappings/, filters.json, config.yaml,
                         comparison.json | diff_ingest.json
  rules/                 known_discrepancies.json (single source of KD logic), custom_rules.py
  input/<role>/ reference/<name>/   drop folders with README per dataset (git-ignored)
  db/ output/ logs/      local DB, reports, LLM batches/findings, review feedback (git-ignored)
  scripts/parity.py      CLI: init-db, precheck, load, filter, compare|ingest-diff, classify,
                         llm-export, llm-import, report, review-import, status, query, run
  parity_core/           engine (copied from core/, upgrade with --upgrade-core)
  docs/                  USER_MANUAL.md, ANALYSIS_FLOW.md (generated from the spec)
```

## Mandatory prerequisites before analysis

1. The agent reads the generated project configuration and mappings; Python parsing scripts perform the data work.
2. `init-db` creates the local SQLite database, core tables, and `raw_<dataset>` tables with all mapped columns.
3. `precheck` verifies input files, table names, mapped columns, dependencies, connectivity, and snapshot declarations.
4. `load` parses source/target/difference/reference files and stores raw values in their configured tables.
5. Required reference snapshots are declared in `config/config.yaml` under `analysis_snapshots` and must be loaded into non-empty filtered tables before classification or LLM analysis.

## Maintaining the factory

| Path | Purpose |
|---|---|
| `core/parity_core/` | Generic engine (Python 3.9+, pandas, openpyxl; DuckDB optional) |
| `templates/project/` | Rendered project files (`{{placeholders}}`, `.modeA.`/`.modeB.` variants, `__slug__`) |
| `factory/` | `new_project.py` generator, `inspect_sample.py` |
| `examples/` | Example specs + sample data (also test fixtures) |
| `.github/` | Designer agent, factory skill, factory rules |
| `tests/` | `python -m unittest discover -s tests -v` |

Change the engine or templates → run the tests → regenerate projects with `--upgrade-core` (engine only) or `--force` (everything; data and custom rules kept, previous config backed up).
