---
name: Analyze PM000003 KD Candidates
description: Analyze only unresolved PM000003 candidates using supplied deterministic and evidence data, returning validated JSON findings.
agent: Project1 LLM Analyst
argument-hint: Candidate batch JSON path, run/day, and approved evidence files
---

Use only the supplied candidate records and evidence.

- Analyze only `POTENTIAL_ISSUE` and `IMS_DATA_ISSUE` rows.
- Never reclassify `EXPECTED` rows.
- Require evidence before assigning any KD code.
- Count logical groups, not raw directional rows.
- Do not claim private Confluence or external data was consulted.
- Keep KD-2, KD-8, KD-9, KD-10, and KD-11 unresolved when their required evidence is absent.
- Return `INSUFFICIENT_EVIDENCE` when deterministic evidence is not improved.
- Distinguish a probable KD assignment from a confirmed assignment.

Return only JSON:

```json
{
  "findings": [
    {
      "row_id": 1,
      "classification": "POTENTIAL_ISSUE",
      "kd_code": null,
      "confidence": 0.45,
      "hypothesis": "...",
      "supporting_evidence": {},
      "missing_evidence": [],
      "confirmation_steps": []
    }
  ]
}
```
