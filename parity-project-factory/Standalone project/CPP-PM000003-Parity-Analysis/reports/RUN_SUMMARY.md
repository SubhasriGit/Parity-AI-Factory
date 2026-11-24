# Synthetic PM000003 Run Summary

This report contains synthetic values only. Store, product, deal, price, packet, message, and timestamp identifiers are unrelated to production data.

## Coverage

- Run period: 2026-11-16 through 2026-11-20
- Synthetic stores: 5
- Source log rows: 50
- Parsed mismatch rows: 250
- Logical groups: 220
- Paired mismatches: 30
- CPP packets: 100
- CPP-derived evidence rows: 200

## Classification

| Classification / KD | Rows |
|---|---:|
| EXPECTED / KD-1 | 10 |
| EXPECTED / KD-2 | 50 |
| EXPECTED / KD-6 | 40 |
| EXPECTED / KD-8 | 25 |
| EXPECTED / KD-9 | 50 |
| EXPECTED / KD-10 | 25 |
| POTENTIAL_ISSUE / no KD | 50 |

Aggregate:

- EXPECTED: 200 (80%)
- POTENTIAL_ISSUE: 50 (20%)
- IMS_DATA_ISSUE: 0 in this synthetic scenario

## Quality

- Malformed source rows: 0
- Mismatch rows: 250
- Verdict rows: 250
- Workbook rows: 250
- Reconciliation: 100%
- LLM candidates: 50

## Data Replacement Statement

The prior project-local CPP CSVs, mismatch CSVs, populated analysis database, generated data-bearing workbooks, and analysis JSON have been replaced. Original files were copied to the external folder `CPP-Private-Originals` outside the project directory for recovery. The active project database and inputs use only synthetic stores in the 5101-5505 range and synthetic products in the 7001000 series.
