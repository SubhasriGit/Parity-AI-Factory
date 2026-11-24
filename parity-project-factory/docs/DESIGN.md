# Parity Project Factory — Design

Status: v1 (core 1.0.0). Audience: the parity team (design review), future maintainers.
Sources: pipeline discussions of 14-Oct-2026 and 13-Nov-2026, the Parity 3 working notes, and the PM000003 mismatch-analysis project.

## 1. Problem and goal

Every parity project (CPP vs IMS price packets, step-2/step-3 L4L parity, future PP parity, …) has rebuilt the same things: getting files, parsing them, loading a local DB, filtering, comparing, classifying known discrepancies, asking an LLM about the rest, and producing reports. PM000003 showed that this works well with **scripts + a local DB + small orchestrating agents**, but it was built by hand and its logic grew in several places at once.

The factory turns that experience into a **template generator**: a designer agent interviews the user, writes a confirmed spec, and a deterministic generator creates a **new, standalone project** (own folder or repository) with folders, configuration, rules, agents, skills, docs and a tested engine. The factory itself does not run parity; the generated project does.

## 2. Two stages of the parity workflow

```text
Raw source file + raw target file (required on both paths)
    |
    v
Validate and load both extracts into the local database
    |
    +-- No mismatch report yet
    |       |
    |       v
    |   Apply user-defined filters (if configured)
    |       |
    |       v
    |   STAGE 1: Compare on configured keys and fields
    |       |
    |       v
    |   Generated mismatch results -------------------------+
    |                                                        |
    +-- Mismatch report already available (current project)  |
            |                                                |
            v                                                |
        Ingest the supplied report; skip comparison --------+
                                                             |
                                                             v
                                         Prepare evidence before Stage 2:
                                         - Both raw extracts available
                                         - Required enrichment data loaded
                                           and validated
                                                             |
                                                             v
                                         STAGE 2: Analyse mismatches
                                         2.1 Deterministic analysis
                                         2.2 LLM analysis of selected candidates
                                                             |
                                                             v
                                                  Mismatch analysis report
```

| Stage | Required inputs | What the project does |
|---|---|---|
| **1 — Generate the parity mismatch report** | Raw source and target files; user-defined filtering rules if needed | Load both files, apply any configured filters, compare the in-scope records on the configured keys, then pass the mismatches to Stage 2. |
| **2 — Analyse the parity mismatches** | Both raw extracts, the mismatch report (generated or supplied), and all enrichment datasets required for the project | Run deterministic analysis first, then use LLM analysis for candidates selected by the project. Publish an analysis report that reflects both steps. |

- **Start at Stage 1** when there is no mismatch report yet. The end-to-end flow runs Stage 1 and then Stage 2.
- **Start at Stage 2** when a mismatch report is already available. Load the raw files for analysis, but do not rerun the source-to-target comparison.

**Current project: start at Stage 2.** An upstream tool supplies the mismatch report. Both raw extracts and all enrichment data required for analysis must be ready before Stage 2 runs.

The configuration labels `A` and `B` identify these entry points: `A` starts with source/target comparison; `B` starts by ingesting a supplied report. They are not separate kinds of parity. A project that needs both uses mode `AB` in one folder and one database. Each full run explicitly selects `--workflow compare` or `--workflow ingest-diff`; both workflows converge on the same `parity_result` table and classification pipeline.

### User-defined filters before comparison

The Parity Project Designer asks whether either dataset needs filtering. The user defines and confirms the business logic: which dataset each rule applies to, which records to include or exclude, and why. For example, the user might exclude test stores from both datasets. The Designer records the confirmed rules in the project spec; the generator writes them to [`config/filters.json`](./SPEC_REFERENCE.md#filters--configfiltersjson) in the generated project. The Designer does not infer exclusion rules.

The pipeline keeps the raw rows unchanged and applies configured rules to the comparison inputs before matching. If there are no rules, no rows are excluded by business filters. When starting at Stage 2 with an existing report, check its comparison scope rather than rerunning the comparison with new filters.

### What passes between the stages

- **Stage 1** uses the configured record keys and field mappings to identify what differs: a missing record, a value difference, or a duplicate key. In an end-to-end run, the current engine passes these results to Stage 2 through the `parity_result` table using the same `run_id`; a separate file hand-off is not needed.
- **Stage 2** starts with those stored results or maps an upstream report into the same result table. It uses the original source and target records to investigate *why* the reported differences occurred. For example, a rule can use the record key to look up both raw prices and check an optional reference snapshot before classifying a price difference.
- **A mismatch report** lists what differed. The **mismatch analysis report** adds the classification, supporting evidence or explanation, and items that still need investigation.

For the current project, validate that the report and both extracts cover the same comparison scope and snapshot before classifying mismatches. The existing Mode B demo shows report ingestion and analysis with a reference snapshot; its sample configuration does not yet include both raw extracts required by this design.

### Prepare enrichment data before Stage 2

The user defines which enrichment datasets the analysis needs (for example, a price-master snapshot or event history) and how to link them to the mismatch records. This preparation applies whether the mismatch report was generated in Stage 1 or supplied directly.

Load all required enrichment datasets and verify their required fields, lookup keys, and relevant snapshot dates or coverage. Their required/optional status, dataset, filtered table, lookup keys, and snapshot date column are declared in `config/config.yaml` under `analysis_snapshots`. If a required dataset is missing, its filtered table is empty, or schema validation fails, report the issue and do not start classification or LLM analysis until it is resolved.

## 3. Design principles (agreed in the discussions)

1. **Scripts do the work; agents are micro-orchestrators.** Agents take the user's intent ("rerun analysis for yesterday's snapshot"), pick files and parameters, and call scripts. Scripts are written once, tested, and then only fixed or extended, never regenerated per run.
2. **Configuration over code.** Project specifics live in JSON config and rules; the engine is domain-independent. Adopting the framework means changing parameters, not scripts.
3. **Everything is persisted in a local DB, stage by stage.** Raw data, filtered data, results, verdicts. Any stage can be rerun alone (e.g. after fixing a rule, rerun from `classify` without reloading gigabytes).
4. **Raw data is kept exactly as received.** Typing and normalisation happen only right before comparison.
5. **Deterministic first, LLM last.** Everything that can be proven with data and SQL is a rule. The LLM reviews only results in the configured candidate classifications, in prioritised batches.
6. **Humans close the loop.** Manual review verdicts override automation, and the disagreements feed back into rules and prompts. Several dry runs on the same data are expected before a project is stable.
7. **Ask, don't assume.** Designer and orchestrator agents ask the user whenever something is ambiguous.

## 4. Architecture

```text
FACTORY: design and generate                                  PROJECT: run parity
----------------------------------                            -------------------------
Parity Project Designer                                       Standalone project folder
  |                                                           |
  v                                                           +-- .github/     Agents and instructions
Confirmed project spec                                        +-- config/      Inputs, keys, report mapping
  |                                                           +-- rules/       Known discrepancy rules
  v                                                           +-- scripts/     Pipeline commands
factory/new_project.py ---- Generate project ---------------> +-- parity_core/ Engine copy
  ^                                                           +-- input/       Raw files and supplied report
  |                                                           +-- reference/   Optional evidence files
  +-- templates/project/    Project blueprints                 +-- db/          Stored inputs and results
  +-- core/parity_core/      Shared engine                     +-- output/      Reports and review files
```

- Open the **factory folder** to design or generate a project. Open the **standalone project folder** to configure or run parity. The factory does not process a project's input files.
- The spec records input layouts, record keys, filters, how to generate or ingest mismatches, and the rules and report settings. The generator turns these into the project's `config/` and `rules/` files without embedding project-specific logic in the shared engine.
- The engine is **vendored** into each project, so projects run standalone and are not broken by factory changes. `--upgrade-core` updates it deliberately.
- Regeneration (`--force`) keeps all data and `custom_rules.py`, and backs up config/rules/agents/docs first.

## 5. Pipeline (mapping to the agreed steps)

| Agreed step | Stage / command | Output |
|---|---|---|
| 0.1 Create DB, check schema, keep existing data | `init-db`, `precheck` | SQLite/selected DB with core tables, `raw_<dataset>` tables, mapped columns, and config/input/schema validation |
| 0.2 Load enrichment datasets required for Stage 2 | `load` (datasets with role `reference`) | `raw_<dataset>` |
| 1 Get raw source and target files for either entry point; also get the mismatch report when starting at Stage 2 | connector `local` + folder README | files in `input/…` |
| 2 Layout/mapping per file | `config/mappings/*.json` | — |
| 3 Save raw data to the local DB | `load` | `raw_<dataset>` + `_loads` audit |
| 4–5 Apply user-defined filters if configured, before comparison | `filter` | `flt_<dataset>` + per-rule counts |
| 6 Generate mismatches or ingest an existing report | `compare` (start at Stage 1) / `ingest-diff` (start at Stage 2) | new `run_id` |
| 7 Save results | — | `parity_result`, run stats |
| 8 Deterministic analysis (Stage 2.1), after required enrichment data has been validated | `classify` | `verdict` (source `rule`) |
| Before the LLM pass: publish the deterministic baseline, as in PM000003 | `report` run after `classify` | Workbook and summary with rule verdicts |
| 9 LLM analysis (Stage 2.2) of candidates selected by classification | `llm-export` → LLM Analyst agent → `llm-import` | `verdict` (source `llm`) |
| 10 Publish or refresh the report after the LLM pass | `report` | Excel + CSV |
| 11 Manual analysis | `review-import` | `verdict` (source `manual`) + feedback file |

`run --from X --to Y --skip Z` runs any sub-sequence.

### Stage 2: Two analysis steps

The working **PM000003 analysis flow** is the reference for this sequence. Its eight steps are preparation, analysis, and reporting activities within the factory's Stage 2 entry path, not eight additional top-level parity stages. When Stage 1 generated the mismatch results, reuse them instead of parsing a second report.

```text
Preparation: load and validate both raw extracts and required snapshots
    |
    v
Parse and pair opposite-direction mismatches on the logical key
    |  Or reuse results already produced by Stage 1
    v
Persist mismatch rows with stable keys for joining to evidence
    |
    v
2.1 Deterministic analysis
    |  Build scoped enrichment lookups
    |  Apply ordered KD rules; first full match wins
    v
Write the deterministic workbook and summary
    |
    v
2.2 LLM analysis
    |  Select candidates by configured classification
    |  Import validated findings; keep prior verdict if unsupported
    v
Write back supported findings and refresh the published summary
    |
    v
Potential issues queue for human review
```

| Working PM000003 step | How it informs the factory design |
|---|---|
| 1. Load snapshots | Load the raw extracts and required evidence into the analysis DB. Validate the keys, fields, and scope before analysing mismatches. |
| 2–3. Parse and persist mismatches | For a supplied report, parse both directions, pair by the configured logical key, and persist the rows for evidence joins. The reference flow uses `mismatch_input`; the factory uses `parity_result` keyed by `run_id`. Initial heuristic `possibleCause` text is not a verified verdict. |
| 4. Deterministic enrichment | After mismatch keys are known, prepare reusable lookups scoped to the affected records. PM000003 uses regular, promo, and staging price lookups, store-to-zone mappings, and parsed CPP packet bodies. These datasets and lookup keys are project-specific. |
| 5. Deterministic KD classification | Apply known-discrepancy (KD) rules in project-defined priority order; the first fully supported match wins. Capture classification, KD code, confidence, and supporting evidence. If no rule matches, mark the row `POTENTIAL_ISSUE` and record what evidence is missing. |
| 6–7. Enriched workbook and summary | The PM000003 workbook keeps its directional analysis sheets, replaces heuristic `possibleCause` with the deterministic verdict, and adds hidden `kdCode` and `classification` columns. The summary includes store totals, breakdowns by store, price type, classification and KD code, and a potential-issues sheet for triage. |
| 8. LLM second pass | PM000003 selects `POTENTIAL_ISSUE` and `DATA_ISSUE` rows. The LLM returns structured findings; it does not edit the workbook. The orchestrator writes back validated findings to `possibleCause` and `possibleCauseDetails` in that workbook workflow. `INSUFFICIENT_EVIDENCE` leaves the deterministic verdict unchanged. |

The reference workflow uses the workbook for candidate selection and write-back. The factory uses DB verdicts and JSON batch/finding files, then regenerates reports so the detail and summary agree. The PM000003 lookup tables, workbook layout, and missing-evidence fields are reference requirements, not generic features implemented by this documentation change.

If evidence is insufficient or no LLM finding is available, the deterministic verdict remains visible. A manual verdict takes precedence when imported; regenerate the report to include it. If only a rule changes and the run's inputs and mismatch results are still valid, rerun from `classify` instead of reloading or comparing the files.

**Parity 3 open question — filter before saving or after?** Decision: **save raw first, then filter into a separate table.** Raw data stays reviewable and re-filterable when rules change, without re-reading files; filtered tables are rebuilt cheaply in SQL.

## 6. Data handling

- **Load policies** per dataset: `replace` (table reflects only the newest file — master tables) or `append` with `dedupe_on` columns (history accumulates, overlapping snapshots are de-duplicated — staging/event tables). This is exactly the PM000003 behaviour (truncate masters, dedupe packets/staging), now configurable.
- **Idempotent loads:** each file's SHA-256 is recorded in `_loads`; identical files are skipped unless `--force`.
- **Atomic replace (SQLite):** delete and insert happen in one transaction; a failed load leaves the previous data intact.
- **Batches:** `processing.batch_size` (default 50,000) drives streaming reads and inserts in every stage, so memory stays flat for multi-million-row files (the approach that solved the PRC out-of-memory problem).
- **Filter scope:** `latest_load` (default for source/target/diff) compares only the newest snapshot even in append tables; `all` (default for reference) uses the whole history.
- **Normalisation before comparison:** zero padding, case, trimming, null tokens, decimal scale and tolerance, per-side date formats. Invalid values become `INVALID(<raw>)` so they surface as mismatches instead of crashing the run.
- **Result types:** `MISMATCH` (one row per record listing all differing fields — e.g. dealer price, retail price, effective date), `MISSING_IN_TARGET`, `MISSING_IN_SOURCE`, `DUPLICATE_KEY_SOURCE/TARGET`. Matches are counted only.
- **Mode B pairing:** opposite-direction rows with the same normalised key are paired into one `MISMATCH`, which avoids treating a value difference as two missing records (a key PM000003 lesson).

## 7. Classification and LLM contract

- `rules/known_discrepancies.json` is the **single source of truth** for known discrepancies. The classifier executes it, the LLM batches embed it, the report shows it, and `ANALYSIS_FLOW.md` is generated from it. This fixes the PM000003 issue where KD logic was split across the Python script, the prompt and the flow document.
- A rule = `applies_to` + `when` (declarative conditions on the result, including `days_diff`, `abs_diff_le`, field-to-field comparison) + optional `sql_check` (read-only SELECT on any local table, e.g. events) + optional `python_check` (escape hatch). Ascending `priority`, first match wins — ordering matters for similar KDs.
- Unmatched results get the default classification (`POTENTIAL_ISSUE`). LLM candidates are selected by configured classification; a project can also include `DATA_ISSUE`, as PM000003 does.
- **LLM hand-off is file-based and validated:** `llm-export` writes `batch_NNN.json` (records + KD catalogue + evidence rows from configured queries + output schema). The LLM Analyst agent writes `findings_NNN.json`; `llm-import` validates run, result ids, classifications and confidence. `INSUFFICIENT_EVIDENCE` keeps the deterministic verdict. `max_rows_per_batch` / `max_batches` cap the cost.
- **Precedence:** manual > llm > rule. All verdicts are kept, so the report shows what each layer said.

## 8. Agents, skills and rules in a generated project

| Kind | Items |
|---|---|
| Orchestrator | `<Project> Orchestrator` — plans (full run, load only, from stage, analysis only, report only, review import), enforces precheck, stops on failure |
| Workers | Setup, Loader, Filter, Comparator (A) or Diff Ingestor (B), Classifier, LLM Analyst, Reporter — each runs one CLI command with a fixed output format |
| Skills | `add-dataset`, `define-known-discrepancy`, `tune-from-review`, `investigate-result` |
| Rules | `.github/copilot-instructions.md` (architecture & behaviour), `.github/instructions/parity-config.instructions.md` (config schema, applied to `config/**` and `rules/**`) |
| Prompt | `/run-parity` → orchestrator |

Factory side: `Parity Project Designer` agent + `create-parity-project` skill.

## 9. Lessons from PM000003 and how the factory addresses them

| PM000003 observation | Factory response |
|---|---|
| KD logic in script, prompt and docs; prompt did not reference the flow doc | One KD file used by classifier, LLM batches, report and generated docs |
| Hard-coded Python path, project names in scripts | Python command from spec; engine has no domain names |
| 1.7 GB DB and CSVs inside the project folder | Data folders are git-ignored by design |
| Ad-hoc scripts (`_inspect_*`, patch files) | `status` and read-only `query` commands; `investigate-result` skill |
| Excel locked during reruns | Clear error asking to close the workbook |
| Manual "Excel corrections → ask Copilot to update prompts" loop | `review-import` produces a structured feedback file + `tune-from-review` skill |

## 10. Scalability options

- **SQLite** (default): simple, single file, fast enough for PM000003-sized data.
- **DuckDB** (optional, `database.engine: "duckdb"`): columnar, faster joins and aggregations for analysis on large data; verified with both example projects. Needs `pip install duckdb`.
- **Large archives (e.g. the 6 GB ProPRC2 full-price file):** recommended next step is converting to **Parquet** and querying it with DuckDB directly (compressed, column-pruned, filterable without full load). Not implemented in v1.
- **Very large comparisons:** the engine streams in batches; if Python becomes the bottleneck, the comparison stage can be replaced by an external engine (e.g. the Java DataFrame-based comparer) as long as it writes the same `parity_result` table.

## 11. Out of scope for v1 / roadmap

1. Connectors beyond local files (FTP, SQL Server/Azure SQL, SFTP, Azure Blob, S3, GCS) — implement per project need. Credentials must come from environment variables or a secret store, never config.
2. Derived columns (e.g. `priceType` from `dealNumber`) at load time.
3. Parquet/DuckDB access to very large reference archives.
4. Consolidated multi-run / management report (PM000003 stage 9).
5. Trend analysis across runs (results are already kept per `run_id`).

## 12. Open questions for review

1. Default classification vocabulary: keep EXPECTED / DATA_ISSUE / POTENTIAL_ISSUE, or align with the PM000003 names (EXPECTED / IMS_DATA_ISSUE / POTENTIAL_ISSUE) per project? option1
2. Should the LLM Analyst run automatically inside a full run, or always wait for explicit user approval (token cost)? automatically but the agents should be flexible from any step as user request
3. Which connector should be implemented first? **Decision for the current project:** Use the existing local-file connector for the supplied mismatch report, both required raw extracts, and any supporting reference files. FTP remains an optional roadmap item for projects that need it.
4. Where should generated projects live by default (one repository per project vs one repository with a folder per project)?
