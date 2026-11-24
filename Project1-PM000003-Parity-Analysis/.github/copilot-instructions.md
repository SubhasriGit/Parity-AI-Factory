# Project1 PM000003 instructions

This repository is a standalone PM000003 parity-analysis project. The uploaded recreation brief is the requirements baseline.

## Non-negotiable behavior

- Never assume a missing contract, filename, rule, store/day mapping, schema detail, or report layout.
- Ask a focused question when required information is absent or contradictory, and record the confirmed answer before implementation.
- Use scripts for data processing; agents coordinate and validate.
- The orchestrator can run the full pipeline or one named task independently.
- A task may start from the middle only when its declared prerequisites have recorded successful evidence or the user explicitly supplies equivalent verified inputs.
- Stop on the first failed dependency and report `BLOCKED`, `FAILED`, `PARTIAL`, or `SUCCESS` with evidence.
- Do not use real production data in tests. Use synthetic masked fixtures.
- Do not commit credentials, production exports, populated databases, or sensitive reports.
- Keep raw, filtered, result, deterministic, LLM, and manual-review evidence traceable by run identifier.
- Final human-reviewed output must be distinguishable from working automated reports.

## Source of truth

1. Confirmed values in `config/project1.yaml`.
2. `docs/CONFIRMED_REQUIREMENTS.md`.
3. Uploaded PM000003 recreation brief.
4. Checked-in schema and tests.

If these conflict, stop and ask the user rather than choosing an interpretation.
