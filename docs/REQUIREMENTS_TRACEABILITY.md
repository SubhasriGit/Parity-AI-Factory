# Requirements Traceability

| Requirement Area | Mandatory Outcome | Planned Task | Status |
|---|---|---|---|
| Source of truth | Uploaded recreation brief governs mandatory behavior | requirements-confirm | CONFIRMED FOR SCAFFOLD |
| Project separation | Standalone project, not part of factory runtime | requirements-confirm | DONE |
| No assumptions | Clarification gate completed; run-specific inputs still require explicit evidence | requirements-confirm | SUCCESS |
| SQLite schema | Checked-in executable canonical DDL and version validation | db-init | SUCCESS |
| CPP snapshots | Idempotent streamed snapshot loading and metadata | cpp-load | SUCCESS |
| IMS migration | Explicit store/day mappings, deduplication, parity validation, backup | ims-migrate | SUCCESS |
| Mismatch parsing | DTO extraction, normalization, malformed-row accounting, pairing | report-parse | SUCCESS |
| Snapshot evidence | Retrieve and persist required CPP/IMS evidence in SQLite | cpp-load, ims-migrate | SUCCESS |
| Packet evidence | Rebuild canonical CPP packet-derived rows | cpp-explode | SUCCESS |
| KD classification | First-match KD-1 through KD-11 priority with evidence gates | classify | SUCCESS |
| LLM analysis | Validated JSON for unresolved rows only | llm-review | SUCCESS |
| Human review | Manual verdict import with precedence retained | human-review-import | SUCCESS |
| Final report | Separate directional/analysis sheets and summary counts | final-report | SUCCESS |
| Validation | DB, workbook, test, count, and evidence checks | validate | SUCCESS |
| Consolidation | Explicitly selected report consolidation | consolidate | OPTIONAL / SUCCESS |

Any change to a confirmed requirement must identify the affected task, tests, configuration, and documentation in `docs/CONFIRMED_REQUIREMENTS.md`.
