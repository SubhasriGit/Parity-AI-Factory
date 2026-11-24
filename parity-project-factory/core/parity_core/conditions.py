"""Declarative conditions used by filters (SQL) and classification rules (records).

Condition grammar (JSON):

    {"all": [cond, ...]}            every condition true
    {"any": [cond, ...]}            at least one true
    {"not": cond}                   negation
    {"field": "<path>", "op": "<op>", "value": <v>}
    {"field": "<path>", "op": "<op>", "field2": "<path>"}   compare two fields

Filter conditions use "column" instead of "field" (a column of the dataset).
Record paths (classification): result_type, mismatch_fields, key.<name>,
source.<column>, target.<column>, details.<field>.source / .target
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional, Tuple

from .db import Database, q

OPS = {
    "eq", "ne", "in", "not_in", "gt", "ge", "lt", "le", "between",
    "contains", "not_contains", "like", "not_like", "regex",
    "is_empty", "not_empty", "days_diff", "abs_diff_le",
}
SQL_OPS = {"eq", "ne", "in", "not_in", "gt", "ge", "lt", "le", "between", "like", "not_like", "is_empty", "not_empty"}
NO_VALUE_OPS = {"is_empty", "not_empty"}


def validate_condition(cond: Any, sql: bool = False, path: str = "when") -> List[str]:
    problems: List[str] = []
    if not isinstance(cond, dict):
        return [f"{path}: condition must be an object"]
    if "all" in cond or "any" in cond:
        key = "all" if "all" in cond else "any"
        if not isinstance(cond[key], list) or not cond[key]:
            return [f"{path}.{key}: must be a non-empty list"]
        for i, sub in enumerate(cond[key]):
            problems.extend(validate_condition(sub, sql, f"{path}.{key}[{i}]"))
        return problems
    if "not" in cond:
        return validate_condition(cond["not"], sql, f"{path}.not")
    if sql and "sql" in cond:
        return []
    target_key = "column" if sql else "field"
    if target_key not in cond:
        return [f"{path}: missing '{target_key}'"]
    op = cond.get("op", "eq")
    allowed = SQL_OPS if sql else OPS
    if op not in allowed:
        return [f"{path}: unsupported op '{op}' (allowed: {', '.join(sorted(allowed))})"]
    if op not in NO_VALUE_OPS and "value" not in cond and "field2" not in cond:
        problems.append(f"{path}: op '{op}' needs 'value'" + ("" if sql else " or 'field2'"))
    if op in ("in", "not_in", "between") and "value" in cond and not isinstance(cond["value"], list):
        problems.append(f"{path}: op '{op}' needs a list value")
    return problems


# ---------------------------------------------------------------------------
# SQL rendering (filters)
# ---------------------------------------------------------------------------


def to_sql(cond: dict, db: Database) -> Tuple[str, list]:
    if "all" in cond or "any" in cond:
        key = "all" if "all" in cond else "any"
        parts, params = [], []
        for sub in cond[key]:
            s, p = to_sql(sub, db)
            parts.append(f"({s})")
            params.extend(p)
        joiner = " AND " if key == "all" else " OR "
        return joiner.join(parts), params
    if "not" in cond:
        s, p = to_sql(cond["not"], db)
        return f"NOT ({s})", p
    if "sql" in cond:
        return str(cond["sql"]), list(cond.get("params", []))

    column = q(cond["column"])
    op = cond.get("op", "eq")
    value = cond.get("value")
    numeric = _is_number(value) or (isinstance(value, list) and value and all(_is_number(v) for v in value))
    expr = db.num(column) if numeric and op in ("eq", "ne", "gt", "ge", "lt", "le", "between", "in", "not_in") else column
    if op in ("is_empty", "not_empty"):
        test = f"({column} IS NULL OR TRIM({column}) = '')"
        return (test if op == "is_empty" else f"NOT {test}"), []
    if op in ("in", "not_in"):
        marks = ", ".join("?" for _ in value)
        sql_op = "IN" if op == "in" else "NOT IN"
        return f"{expr} {sql_op} ({marks})", list(value)
    if op == "between":
        return f"{expr} BETWEEN ? AND ?", [value[0], value[1]]
    if op in ("like", "not_like"):
        return f"{column} {'LIKE' if op == 'like' else 'NOT LIKE'} ?", [value]
    sql_op = {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}[op]
    return f"{expr} {sql_op} ?", [value]


# ---------------------------------------------------------------------------
# Record evaluation (classification)
# ---------------------------------------------------------------------------


def get_path(record: dict, path: str) -> Any:
    current: Any = record
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def evaluate(cond: dict, record: dict) -> bool:
    if "all" in cond:
        return all(evaluate(sub, record) for sub in cond["all"])
    if "any" in cond:
        return any(evaluate(sub, record) for sub in cond["any"])
    if "not" in cond:
        return not evaluate(cond["not"], record)

    op = cond.get("op", "eq")
    left = get_path(record, cond["field"])
    right = get_path(record, cond["field2"]) if "field2" in cond else cond.get("value")

    if op == "is_empty":
        return _empty(left)
    if op == "not_empty":
        return not _empty(left)
    if op in ("contains", "not_contains"):
        found = _contains(left, right)
        return found if op == "contains" else not found
    if op in ("in", "not_in"):
        values = right if isinstance(right, list) else [right]
        found = any(_equal(left, v) for v in values)
        return found if op == "in" else not found
    if op == "regex":
        return left is not None and re.search(str(right), str(left)) is not None
    if op in ("like", "not_like"):
        pattern = "^" + re.escape(str(right)).replace("%", ".*").replace("_", ".") + "$"
        matched = left is not None and re.match(pattern, str(left), re.IGNORECASE) is not None
        return matched if op == "like" else not matched
    if op == "days_diff":
        d1, d2 = _to_date(left), _to_date(get_path(record, cond["field2"]) if "field2" in cond else None)
        if d1 is None or d2 is None:
            return False
        expected = cond.get("value", 1)
        return abs((d1 - d2).days) == int(expected)
    if op == "abs_diff_le":
        a = _to_decimal(left)
        b = _to_decimal(get_path(record, cond["field2"])) if "field2" in cond else None
        tol = _to_decimal(cond.get("value", 0))
        return a is not None and b is not None and tol is not None and abs(a - b) <= tol
    if op == "between":
        return _compare(left, right[0]) >= 0 and _compare(left, right[1]) <= 0 if left is not None else False
    if op == "eq":
        return _equal(left, right)
    if op == "ne":
        return not _equal(left, right)
    if left is None or right is None:
        return False
    cmp = _compare(left, right)
    return {"gt": cmp > 0, "ge": cmp >= 0, "lt": cmp < 0, "le": cmp <= 0}[op]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return str(value).strip() == ""


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _equal(left: Any, right: Any) -> bool:
    if isinstance(left, list) and isinstance(right, list):
        return sorted(map(str, left)) == sorted(map(str, right))
    if isinstance(left, list):
        left = ",".join(map(str, left))
    if left is None or right is None:
        return _empty(left) and _empty(right)
    a, b = _to_decimal(left), _to_decimal(right)
    if a is not None and b is not None:
        return a == b
    return str(left).strip() == str(right).strip()


def _compare(left: Any, right: Any) -> int:
    a, b = _to_decimal(left), _to_decimal(right)
    if a is not None and b is not None:
        return (a > b) - (a < b)
    sa, sb = str(left), str(right)
    return (sa > sb) - (sa < sb)


def _contains(container: Any, item: Any) -> bool:
    if container is None:
        return False
    if isinstance(container, list):
        items = item if isinstance(item, list) else [item]
        return all(any(str(c) == str(i) for c in container) for i in items)
    return str(item) in str(container)
