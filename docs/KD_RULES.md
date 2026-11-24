# Deterministic KD Rules

The classifier in `scripts/classify_kd.py` enforces this first-match order:

1. KD-7: IMS duplicate effective-date artifact
2. KD-4: future promo already present in IMS
3. KD-3: promo cross-day timing
4. KD-1: confirmed one-sided dealer/retail update
5. KD-5: multiple override zones with divergent prices
6. KD-9: possible promo override deletion
7. KD-6: regular master has both change types as Initial Price
8. KD-10: same amounts, changed effective date
9. RAW_PARITY: raw prices match but key/date representation differs
10. RAW_MISMATCH_SAME_DAY: same-day IMS/CPP prices differ
11. KD-2: missing matching CPP master evidence
12. KD-8: unavailable product/deal/store participation evidence
13. Fallback: unmatched potential issue

## Evidence Rules

- KD-2, KD-8, KD-9, and KD-10 are classified as `EXPECTED` when their known discrepancy pattern matches. Question-mark KD suffixes are not used.
- Missing `priceChangeEvent`, `product_deal_store_rel`, deletion history, packet/IMS lineage, or IMS application history does not downgrade the classification. It sets `confirmation_status = CONFIRMATION_REQUIRED` and records the exact reviewer recommendation in `confirmation_reason`.
- Only rows that do not match a known KD remain `POTENTIAL_ISSUE`.
- Truncated or malformed packet JSON cannot produce confirmed evidence.
- Manual review overrides LLM; LLM overrides deterministic verdict only after validated supporting evidence.
- Confidence measures evidence strength, not proof of business taxonomy.

Every verdict stores classification, KD code, confidence, hypothesis, supporting evidence, and missing evidence.
