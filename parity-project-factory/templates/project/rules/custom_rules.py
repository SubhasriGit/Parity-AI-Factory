"""Custom checks for rules/known_discrepancies.json (`python_check`).

Use only when a pattern cannot be expressed with `when` conditions and a
`sql_check`. Each function receives the result record and the DB wrapper and
returns False/None (no match), True (match), or a dict with optional
`hypothesis`, `confidence` and `evidence` overriding the rule's defaults.

record = {
  "result_id": int, "result_type": "MISMATCH" | "MISSING_IN_TARGET" | ...,
  "key": {...}, "mismatch_fields": [...], "source": {...} | None,
  "target": {...} | None, "details": {field: {"source": v, "target": v}}
}
db.query(sql, params) -> list of tuples (read-only use only).
"""


def example_check(record, db):
    """Example: never matches. Reference it from a rule as "python_check": "example_check"."""
    return False
