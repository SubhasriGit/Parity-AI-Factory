# Standalone Parity Projects

This folder contains implementation-specific standalone projects generated or maintained with the Parity Project Factory.

Each project is self-contained: it owns its requirements, configuration, agents, schema, scripts, tests, synthetic or approved demonstration data, reports, and a project-specific `README.md`.

## Projects

| Project | Purpose | Status | README |
|---|---|---|---|
| `CPP-PM000003-Parity-Analysis/` | PM000003 mismatch analysis for CPP/CDCS pricing evidence | Implemented and validated | [Open README](CPP-PM000003-Parity-Analysis/README.md) |

## Required README Per Project

Every folder under this directory must have a project-specific `README.md`. A shared README is not a substitute because each implementation has different inputs, keys, rules, snapshots, agents, commands, and outputs.

Start new project documentation from [README_TEMPLATE.md](README_TEMPLATE.md), then replace every angle-bracket placeholder with confirmed project details.

A complete project README must cover:

1. Business purpose and system identity.
2. Confirmed workflow, keys, datasets, and snapshot rules.
3. Input contracts and reference sources.
4. Database, schema, and required tables.
5. Pipeline tasks and independent execution prerequisites.
6. Orchestrator and specialist-agent responsibilities.
7. Exact install, generation, run, resume, status, and validation commands.
8. Checked-in or generated output locations.
9. Human-review, LLM, classification, and rule precedence.
10. Synthetic, anonymized, or production data policy.
11. CI paths and evidence artifacts.
12. A reuse guide and definition of done for a similar project.

## Adding A Similar Standalone Project

```powershell
cd parity-project-factory
python factory/new_project.py --spec specs/<slug>.spec.json --dest "Standalone project/<project-folder>" --with-samples
Copy-Item "Standalone project/README_TEMPLATE.md" "Standalone project/<project-folder>/README.md"
```

Then complete the project-specific design before generating production code:

1. Confirm the request, source systems, owners, workflow mode, matching keys, filters, known discrepancies, and output contract.
2. Update the generated agents, config, schema, and scripts together.
3. Replace README placeholders with the confirmed implementation.
4. Add deterministic tests and synthetic fixtures.
5. Run the full workflow and at least one independent/resumed task.
6. Reconcile database, verdict, workbook, and presentation totals.
7. Scan for secrets and unapproved production data before committing.
8. Update the project index in this README.
9. Update root GitHub Actions paths for the new nested project.

## Design Reuse Boundary

Reuse the folder, documentation, task model, validation gates, and agent pattern. Do not blindly copy project-specific values such as stores, products, dates, CPP/CDCS field mappings, snapshot-day maps, KD rules, database paths, or report metrics.

The factory is the reusable implementation base; each standalone README is the exact design and operating contract for one implementation.
