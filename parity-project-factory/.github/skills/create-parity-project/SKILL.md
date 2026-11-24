---
name: create-parity-project
description: Generate, validate, regenerate or upgrade a parity project with the Parity Project Factory (factory/new_project.py). Use after the requirements have been captured in a spec, or when an existing generated project needs a parity_core upgrade.
---
# Create a parity project with the factory

## Commands (run from the factory root)
| Task | Command |
|---|---|
| Inspect a sample file and draft a mapping | `python factory/inspect_sample.py --file <sample> [--delimiter "\|"] [--fixed-width]` |
| Validate a spec (no output folder) | `python factory/new_project.py --spec specs/<slug>.spec.json --validate-only` |
| Generate a new project | `python factory/new_project.py --spec specs/<slug>.spec.json --dest <folder> [--with-samples] [--git-init]` |
| Regenerate after spec changes | add `--force` (input/, reference/, db/, output/ and rules/custom_rules.py are kept; config, rules, .github, docs and README are backed up to `.factory-backup/<timestamp>/` first) |
| Upgrade only the engine in an existing project | `python factory/new_project.py --dest <folder> --upgrade-core` |

## Writing the spec
1. Start from the closest example: `examples/mode-a-price-compare/spec.json` (compare files) or `examples/mode-b-mismatch-report/spec.json` (analyse a supplied diff report).
2. Fill every section described in `docs/SPEC_REFERENCE.md`. Required: `project` (name, slug, mode), `datasets` with `columns`, and `comparison` (A or AB), `diff_ingest` (B or AB), or both. Use mode `AB` and one destination folder when both workflows belong to the same parity requirement.
3. Keep names snake_case for datasets and columns; never start a column name with `_`.
4. No credentials anywhere; the generator rejects fields such as `password`, `token`, `connectionString`.
5. Add `samples` (dataset -> sample path relative to the spec) when sample files exist. They make dry runs possible right after generation.

## After generating
1. `cd <folder>` then `python scripts/parity.py init-db` and `python scripts/parity.py precheck`.
2. With samples: run `python scripts/parity.py run` for A or B. For AB, explicitly run `--workflow compare` and/or `--workflow ingest-diff`; check result counts and classification distribution with the user.
3. If something is wrong in config, fix the spec and regenerate with `--force`, or edit the generated config directly (then keep the spec in sync for future regenerations).
