# Confirmed Requirements

The blocking P0 requirement gate is **OPEN**. Executable implementation may begin, subject to run-specific inputs and prerequisite validation.

## Confirmed

- This document is the finalized requirements baseline for the implemented project.
- The project is separate from `parity-project-factory`.
- The project prefix is `Project1`.
- The orchestrator must support full-run, resume, and independent middle-task execution.
- Agents must not assume unresolved requirements.
- The PM000003 brief's mandatory schema, loaders, parser, KD order, LLM contract, reports, tests, and documentation remain in scope for the future implementation phase.
- Production inputs, credentials, populated databases, and sensitive reports must not be committed.
- **P0-01:** use the `python` command with minimum Python 3.9.
- **P0-02:** keep runtime data in project-local folders, with configurable path overrides.
- **P1-02:** show both raw directional-row counts and paired logical-group counts.
- **P1-04:** consolidated reporting is optional and on demand, not part of the normal daily run.
- **P0-05:** the user supplies an explicit IMS source-table suffix to ISO snapshot-day mapping for each import. The implementation must never infer an ambiguous mapping.
- **P0-07:** the documented KD-1 through KD-11 matrix and first-match precedence are approved as final.
- **P0-08:** LLM analysis and supported write-back do not require human approval. `INSUFFICIENT_EVIDENCE` remains non-writing.
- **P0-09:** report distribution does not require prior approval; the destination is configurable for each environment or run.
- **P0-10:** only locally available evidence may confirm a rule. Missing `priceChangeEvent`, deal-store participation, deletion history, packet/IMS lineage, or IMS application history keeps KD-2, KD-8, KD-9, KD-10, and KD-11 unresolved with explicit `missing_evidence`.

## Open Run-Specific Inputs

No P0 requirement blocks implementation. Each run must still provide or validate its concrete files, stores, IMS day mapping, database path, and evidence datasets. These are task inputs, not unresolved policy questions.

## Approval Record

| Phase | Approval | Confirmed by | Date |
|---|---|---|---|
| Requirements scaffold | Approved by request | User | 2026-11-23 |
| Schema/scripts implementation | Requirements approved; implementation not started | User requirements confirmation | 2026-11-23 |
