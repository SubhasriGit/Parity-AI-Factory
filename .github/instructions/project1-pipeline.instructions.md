---
applyTo: ".github/agents/**,config/**,scripts/**,schema/**,tests/**,docs/**"
description: "Project1 pipeline orchestration, no-assumption gate, independent task execution, state evidence, and validation rules."
---

# Project1 Pipeline Rules

- Read `config/pipeline.yaml` before planning a task sequence.
- Read `config/project1.yaml` and `docs/CONFIRMED_REQUIREMENTS.md` before coding or execution.
- Treat `docs/CONFIRMED_REQUIREMENTS.md` as the finalized policy source; block only for missing run-specific inputs or failed evidence.
- Do not convert an undocumented preference into a default.
- Independent and middle-task execution requires current prerequisite evidence; do not replay earlier tasks merely for convenience.
- Update `state/task-state.json` through an implementation script when task execution support is added. Agents must not manually fabricate state success.
- Stop on the first failed dependency.
- Run focused validation after each implementation slice.
- Keep schema contracts, data contracts, KD priority, and workbook contracts synchronized across scripts, tests, and documentation.
