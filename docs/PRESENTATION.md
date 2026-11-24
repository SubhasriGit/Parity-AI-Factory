# PM000003 Parity Analysis

## Purpose

Create a repeatable, auditable workflow for explaining differences between CDCS/IMS and CPP pricing data.

## Outcomes

- `EXPECTED`: supported known discrepancy
- `IMS_DATA_ISSUE`: evidence indicates an IMS/CDCS-side data problem
- `POTENTIAL_ISSUE`: unresolved or candidate discrepancy requiring review

## Workflow

1. Capture and normalize mismatch reports.
2. Load five CPP reference snapshots.
3. Migrate explicitly mapped IMS snapshots.
4. Expand CPP packet JSON into canonical evidence.
5. Apply strict deterministic KD precedence.
6. Use LLM review only for selected unresolved cases.
7. Import human review.
8. Publish a reconciled final Excel report.

## Operating Model

The orchestrator can run the full pipeline, resume from state, or run a named task independently. Scripts perform data work. Agents coordinate, validate prerequisites, and report evidence.

## Controls

- No inferred IMS day mapping
- No production data in tests
- No unapproved destructive reload semantics
- Backup before replace/schema reshape
- No confirmed evidence from truncated packets
- Final workbook and database counts reconciled
