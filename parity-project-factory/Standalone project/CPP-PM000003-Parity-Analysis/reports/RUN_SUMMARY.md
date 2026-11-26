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

## Quality

- Malformed source rows: 0
- Mismatch/verdict/workbook rows: 250/250/250
- Reconciliation: 100%
- EXPECTED: 200
- POTENTIAL_ISSUE: 50
- LLM candidates: 50
- Human-approval audit rows: 50

## Runtime And Cost Telemetry

- Full generator runtime: 6.108 seconds
- Analysis pipeline duration before presentation generation: 4.332 seconds
- Recorded command steps: 10
- In-pipeline model requests: 0
- In-pipeline model cost: $0.000000
- Estimated external-LLM hand-off (not billed): 50 candidates in 1 batch(es), ~7366/7500 input/output tokens, ~$0.0934 at `ILLUSTRATIVE_REPLACE_WITH_CONTRACT_PRICE` prices
- Guardrails: redaction on, skipped by cap 0, skipped by spend ceiling 0
- Copilot capture status: `unavailable`
- Copilot requests: 0
- Copilot input/output tokens: 0/0
- Copilot computed cost: unavailable (no Copilot OTEL llm_request events)

The synthetic workflow makes its LLM hand-off through validated JSON and does not call a model API inside the pipeline. Copilot agent-development cost is reported only when `llm_request` OpenTelemetry events and pricing metadata are available.

## Control Evidence

Every `INSUFFICIENT_EVIDENCE` result preserves the deterministic verdict and records `HUMAN_APPROVAL_REQUIRED` in report audit columns without blocking execution or final reporting. Failed tasks retry no more than twice; exhaustion records `HUMAN_INSPECTION_REQUIRED` while automatic resume remains available.
