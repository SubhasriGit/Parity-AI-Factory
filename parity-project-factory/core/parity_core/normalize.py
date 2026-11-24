"""Value normalisation applied right before comparison (raw data stays untouched).

Field spec options (comparison.json keys/fields, diff_ingest.json keys):
  type: string | integer | decimal | date | datetime
  trim: true (default)
  case: "upper" | "lower" | null  (default from options.case_sensitive)
  zero_pad: <width>            left-pad with zeros (string/integer keys like store numbers)
  strip_leading_zeros: true
  null_values: ["", "NULL", ...]   values treated as empty (None)
  format / source_format / target_format: strptime format(s) for dates
  scale: <digits>              round decimals before comparing
  tolerance: <number>          allowed absolute difference for decimals
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

DEFAULT_NULLS = ["", "NULL", "null", "None", "NaN", "nan"]
DATE_FORMATS = ["%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%d-%b-%Y"]
DATETIME_FORMATS = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f"]


def _formats(spec: Dict[str, Any], side: str, defaults: List[str]) -> List[str]:
    value = spec.get(f"{side}_format") or spec.get("format")
    if value is None:
        return defaults
    return value if isinstance(value, list) else [value]


def invalid(raw: str) -> str:
    return f"INVALID({raw})"


def normalize(value: Optional[str], spec: Dict[str, Any], side: str = "source", options: Optional[Dict] = None) -> Optional[str]:
    options = options or {}
    if value is None:
        return None
    text = str(value)
    if spec.get("trim", options.get("trim", True)):
        text = text.strip()
    if text in spec.get("null_values", options.get("null_values", DEFAULT_NULLS)):
        return None
    ftype = spec.get("type", "string")

    if ftype == "string":
        if spec.get("strip_leading_zeros"):
            text = text.lstrip("0") or "0"
        if spec.get("zero_pad"):
            text = text.zfill(int(spec["zero_pad"]))
        case = spec.get("case")
        if case is None and not options.get("case_sensitive", True):
            case = "upper"
        if case == "upper":
            text = text.upper()
        elif case == "lower":
            text = text.lower()
        return text

    if ftype in ("integer", "decimal"):
        cleaned = text.replace(spec.get("thousands", ","), "") if spec.get("thousands", ",") else text
        try:
            number = Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return invalid(text)
        if ftype == "integer":
            if number != number.to_integral_value():
                return invalid(text)
            out = str(int(number))
            return out.zfill(int(spec["zero_pad"])) if spec.get("zero_pad") else out
        if spec.get("scale") is not None:
            number = number.quantize(Decimal(1).scaleb(-int(spec["scale"])), rounding=ROUND_HALF_UP)
        return format_decimal(number)

    if ftype in ("date", "datetime"):
        formats = _formats(spec, side, DATE_FORMATS if ftype == "date" else DATETIME_FORMATS + DATE_FORMATS)
        candidate = text if ftype == "datetime" else text[:10] if len(text) > 10 and text[10] in "T " else text
        for fmt in formats:
            try:
                parsed = datetime.strptime(candidate, fmt)
            except ValueError:
                continue
            return parsed.strftime("%Y-%m-%d") if ftype == "date" else parsed.strftime("%Y-%m-%dT%H:%M:%S")
        return invalid(text)

    return text


def format_decimal(number: Decimal) -> str:
    if number == 0:
        return "0"
    normalized = number.normalize()
    text = format(normalized, "f")
    return text


def values_equal(a: Optional[str], b: Optional[str], spec: Dict[str, Any]) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if a == b:
        return True
    if spec.get("type") == "decimal" and spec.get("tolerance") is not None:
        if a.startswith("INVALID(") or b.startswith("INVALID("):
            return False
        return abs(Decimal(a) - Decimal(b)) <= Decimal(str(spec["tolerance"]))
    return False
