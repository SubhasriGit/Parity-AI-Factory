#!/usr/bin/env python3
"""Parse PM000003 mismatch exports, persist normalized rows, and create daily workbooks."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import PatternFill

DEFAULT_PATTERN = r"PromoDealPriceDto\(dealNumber=(?P<dealNumber>[^,)]*), offeringNumber=(?P<offeringNumber>[^,)]*), effectiveDate=(?P<effectiveDate>[^,)]*), dealerCostPrice=(?P<dealerCostPrice>[^,)]*), retailPrice=(?P<retailPrice>[^,)]*), castingPrice=(?P<castingPrice>[^)]*)\)"
DEFAULT_DIRECTIONS = ("CDCS_missing_in_CPP", "CPP_missing_in_CDCS")
PRICE_TYPE_RULES = [{"rule": "dealNumber != 0", "priceType": "PROMO"}, {
    "rule": "dealNumber = 0", "priceType": "REGULAR"}]
DETAIL_COLUMNS = ("comparisonDirection", "store", "timestamp", "messageId", "priceType", "dealNumber",
                  "offeringNumber", "effectiveDate", "dealerCostPrice", "retailPrice", "castingPrice", "sourceSummary")
ANALYSIS_COLUMNS = ("comparisonDirection", "store", "timestamp", "priceType", "dealNumber", "offeringNumber", "effectiveDate",
                    "dealerCostPrice", "retailPrice", "castingPrice", "possibleCause", "possibleCauseDetails", "classification", "kdCode")


@dataclass(frozen=True)
class MismatchRow:
    comparison_direction: str
    store: str
    timestamp: str
    message_id: str
    price_type: str
    deal_number: str
    offering_number: str
    effective_date: str
    dealer_cost_price: str
    retail_price: str
    casting_price: str
    source_summary: str
    possible_cause: str = ""
    possible_cause_details: str = ""
    classification: str = ""
    kd_code: str = ""

    @property
    def day(self) -> str:
        return parse_timestamp(self.timestamp).date().isoformat()

    @property
    def key(self) -> str:
        return "|".join((self.store, self.offering_number, self.price_type, self.deal_number, self.effective_date))


def parse_timestamp(raw: str) -> datetime:
    for fmt in ("%B %d, %Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            pass
    raise ValueError(f"Invalid input timestamp: {raw}")


def get_field(row: dict, name: str) -> str:
    wanted = name.casefold()
    return next((str(value or "") for key, value in row.items() if key and key.strip().casefold() == wanted), "")


def decimal_text(value: str, field: str) -> str:
    try:
        number = Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"Invalid {field}: {value}") from exc
    return f"{number:.3f}"


def price_type(rules: list, deal_number: str, dealer: str, retail: str, casting: str) -> str:
    context = {"dealNumber": Decimal(deal_number), "dealerCostPrice": Decimal(
        dealer), "retailPrice": Decimal(retail), "castingPrice": Decimal(casting)}
    operators = {">": lambda a, b: a > b, "<": lambda a, b: a < b, ">=": lambda a, b: a >=
                 b, "<=": lambda a, b: a <= b, "!=": lambda a, b: a != b, "=": lambda a, b: a == b}
    for rule in rules:
        terms = re.split(
            r"\s+and\s+", str(rule.get("rule", "")), flags=re.IGNORECASE)
        matched = True
        for term in terms:
            match = re.fullmatch(
                r"([A-Za-z][A-Za-z0-9_]*)\s*(>=|<=|!=|=|>|<)\s*(-?\d+(?:\.\d+)?)", term.strip())
            if not match or operators[match.group(2)](context.get(match.group(1)), Decimal(match.group(3))) is False:
                matched = False
                break
        if matched:
            return str(rule.get("priceType", "UNKNOWN"))
    return "UNKNOWN"


def validate_input_headers(path: Path) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        actual = {str(item).strip().casefold()
                  for item in (reader.fieldnames or []) if item}
    required = {"timestamp", "store", "message", "message id"}
    missing = required - actual
    if missing:
        raise ValueError(f"{path}: missing required columns {sorted(missing)}")


def parse_inputs(csv_inputs: list, pattern: str, price_rules: list) -> tuple[list[MismatchRow], dict]:
    regex = re.compile(pattern)
    rows = []
    malformed = []
    metrics = {"source_rows": 0, "messages_with_dtos": 0,
               "parsed_rows": 0, "malformed_rows": 0}
    for item in csv_inputs:
        direction = str(item["comparisonDirection"])
        path = Path(item["csvPath"]).resolve()
        validate_input_headers(path)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for line_no, source in enumerate(csv.DictReader(handle), start=2):
                metrics["source_rows"] += 1
                try:
                    timestamp = get_field(source, "Timestamp").strip()
                    parse_timestamp(timestamp)
                    store = get_field(source, "Store").strip()
                    if not store:
                        raise ValueError("empty store")
                    message = get_field(source, "Message")
                    matches = list(regex.finditer(message))
                    if not matches:
                        malformed.append(
                            {"direction": direction, "line": line_no, "reason": "no DTO match"})
                        metrics["malformed_rows"] += 1
                        continue
                    metrics["messages_with_dtos"] += 1
                    for match in matches:
                        raw = match.groupdict()
                        deal = str(raw["dealNumber"]).strip()
                        offering = str(raw["offeringNumber"]).strip()
                        int(deal)
                        int(offering)
                        effective = date.fromisoformat(
                            str(raw["effectiveDate"]).strip()).isoformat()
                        dealer = decimal_text(
                            raw["dealerCostPrice"], "dealerCostPrice")
                        retail = decimal_text(
                            raw["retailPrice"], "retailPrice")
                        casting = decimal_text(
                            raw["castingPrice"], "castingPrice")
                        rows.append(MismatchRow(
                            comparison_direction=direction, store=store.zfill(4), timestamp=timestamp,
                            message_id=get_field(source, "Message Id").strip(), price_type=price_type(price_rules, deal, dealer, retail, casting),
                            deal_number=deal.zfill(4), offering_number=offering.zfill(7), effective_date=effective,
                            dealer_cost_price=dealer, retail_price=retail, casting_price=casting,
                            source_summary=direction,
                        ))
                        metrics["parsed_rows"] += 1
                except (ValueError, KeyError) as exc:
                    malformed.append(
                        {"direction": direction, "line": line_no, "reason": str(exc)})
                    metrics["malformed_rows"] += 1
    rows.sort(key=lambda row: (row.day, row.comparison_direction,
              row.store, row.offering_number, row.deal_number))
    return rows, {**metrics, "malformed": malformed}


def pair_rows(rows: list[MismatchRow]) -> list[dict]:
    groups = {}
    for row in rows:
        key = (row.store, row.offering_number, row.price_type,
               row.deal_number, row.effective_date)
        groups.setdefault(key, []).append(row)
    pairs = []
    for key, members in groups.items():
        cdcs = [row for row in members if row.comparison_direction ==
                "CDCS_missing_in_CPP"]
        cpp = [row for row in members if row.comparison_direction ==
               "CPP_missing_in_CDCS"]
        while cdcs and cpp:
            left, right = cdcs.pop(0), cpp.pop(0)
            fields = []
            for field in ("dealer_cost_price", "retail_price", "casting_price"):
                if getattr(left, field) != getattr(right, field):
                    fields.append(field)
            pairs.append({"type": "PAIRED_MISMATCH", "key": key, "left": asdict(
                left), "right": asdict(right), "mismatch_fields": fields})
        for row in cdcs:
            pairs.append({"type": "CDCS_missing_in_CPP", "key": key,
                         "row": asdict(row), "mismatch_fields": []})
        for row in cpp:
            pairs.append({"type": "CPP_missing_in_CDCS", "key": key,
                         "row": asdict(row), "mismatch_fields": []})
    return pairs


def persist_rows(connection: sqlite3.Connection, rows: list[MismatchRow]) -> dict:
    connection.execute("DELETE FROM mismatch_verdict")
    connection.execute("DELETE FROM mismatch_input")
    values = [(
        row.day, row.comparison_direction, row.store, row.offering_number, row.deal_number,
        row.price_type, row.effective_date, row.dealer_cost_price, row.retail_price,
        row.casting_price, parse_timestamp(row.timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"), row.message_id,
    ) for row in rows]
    connection.executemany(
        "INSERT INTO mismatch_input(day,direction,store,offering_number,deal_number,price_type,effective_date,dealer_cost_price,retail_price,casting_price,timestamp_utc,message_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        values,
    )
    days = sorted({row.day for row in rows})
    counts = {day: sum(row.day == day for row in rows) for day in days}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metadata = {
        "mismatch_input.analysisDate": max(days) if days else "",
        "mismatch_input.days": json.dumps(days),
        "mismatch_input.rowCountsByDay": json.dumps(counts),
        "mismatch_input.loadedAtUtc": now,
        "mismatch_input.rowCount": str(len(rows)),
    }
    connection.executemany(
        "INSERT INTO _metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        list(metadata.items()),
    )
    return {"rows": len(rows), "days": counts}


def safe_sheet(name: str, workbook: Workbook) -> str:
    name = re.sub(r"[\\/*?:\[\]]", "_", name)[:31] or "Details"
    existing = set(workbook.sheetnames)
    if name not in existing:
        return name
    index = 1
    while f"{name[:28]}_{index}" in existing:
        index += 1
    return f"{name[:28]}_{index}"


def write_daily_workbook(rows: list[MismatchRow], output: Path, metrics: dict) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    summary.append(["metric", "value"])
    for key in ("source_rows", "messages_with_dtos", "parsed_rows", "malformed_rows"):
        summary.append([key, metrics[key]])
    groups = {}
    for row in rows:
        groups.setdefault(row.comparison_direction, []).append(row)
    fill = PatternFill(fill_type="solid", fgColor="D9D9D9")
    for direction in DEFAULT_DIRECTIONS:
        sheet = workbook.create_sheet(safe_sheet(direction, workbook))
        sheet.append(list(DETAIL_COLUMNS))
        for cell in sheet[1]:
            cell.fill = fill
        for row in groups.get(direction, []):
            sheet.append([row.comparison_direction, row.store, row.timestamp, row.message_id, row.price_type,
                          row.deal_number, row.offering_number, row.effective_date, row.dealer_cost_price,
                          row.retail_price, row.casting_price, row.source_summary])
        analysis = workbook.create_sheet(
            safe_sheet(direction + "_analysis", workbook))
        analysis.append(list(ANALYSIS_COLUMNS))
        for cell in analysis[1]:
            cell.fill = fill
        for row in groups.get(direction, []):
            analysis.append([row.comparison_direction, row.store, row.timestamp, row.price_type,
                             row.deal_number, row.offering_number, row.effective_date, row.dealer_cost_price,
                             row.retail_price, row.casting_price, "", "", "", ""])
    workbook.save(output)
    return output


def load_config(path: Optional[Path]) -> dict:
    if path is None:
        raise ValueError("--config is required for the project run")
    config = json.loads(path.read_text(encoding="utf-8"))
    validate_config(config)
    return config


def validate_config(config: dict) -> None:
    inputs = config.get("csv_inputs") or []
    directions = [str(item.get("comparisonDirection", "")) for item in inputs]
    if set(directions) != set(DEFAULT_DIRECTIONS) or len(directions) != 2:
        raise ValueError(
            f"csv_inputs must contain exactly {list(DEFAULT_DIRECTIONS)} without duplicate directions")
    rules = config.get("priceTypeRules") or []
    if not isinstance(rules, list) or not rules:
        raise ValueError("priceTypeRules must be a non-empty list")
    for rule in rules:
        if not isinstance(rule.get("rule"), str) or not isinstance(rule.get("priceType"), str):
            raise ValueError(
                "Each priceTypeRules item needs string rule and priceType values")
    allowed_columns = set(DETAIL_COLUMNS) | set(ANALYSIS_COLUMNS)
    for key in ("detailColumns", "analysisColumns"):
        values = config.get(key)
        if values is not None:
            unknown = set(values) - allowed_columns
            if unknown:
                raise ValueError(
                    f"{key} contains unknown columns {sorted(unknown)}")
    output = config.get("outputPath")
    if not isinstance(output, str) or not output.strip():
        raise ValueError("outputPath must be a non-empty string")


def run(config_path: Path, db_path: Optional[Path], output_override: Optional[Path], analysis_date: Optional[str] = None) -> dict:
    config = load_config(config_path)
    config_dir = config_path.parent.resolve()
    project_root = config_dir.parent if config_dir.name == "config" else config_dir
    inputs = config.get("csv_inputs") or []
    if not inputs:
        raise ValueError(
            "config.csv_inputs must contain the two directional exports")
    normalized_inputs = []
    for item in inputs:
        normalized = dict(item)
        path = Path(normalized["csvPath"])
        if path.is_absolute():
            normalized["csvPath"] = str(path)
        elif config_dir.name == "config":
            candidate = (config_dir / path).resolve()
            normalized["csvPath"] = str(
                candidate if candidate.exists() else (project_root / path).resolve())
        else:
            normalized["csvPath"] = str((project_root / path).resolve())
        normalized_inputs.append(normalized)
    rows, metrics = parse_inputs(normalized_inputs, config.get(
        "parserPatternRegex", DEFAULT_PATTERN), config.get("priceTypeRules", PRICE_TYPE_RULES))
    if analysis_date:
        rows = [row for row in rows if row.day == analysis_date]
    if not rows:
        raise ValueError("No parsed rows for the requested input/day")
    by_day = {}
    for row in rows:
        by_day.setdefault(row.day, []).append(row)
    output_base = Path(output_override) if output_override else Path(config.get(
        "outputPath", "reports/pm000003_mismatch_analysis.xlsx"))
    if not output_base.is_absolute():
        output_base = (project_root / output_base).resolve()
    outputs = []
    for day, day_rows in sorted(by_day.items()):
        target = output_base.with_name(
            f"{output_base.stem}_{day}{output_base.suffix}")
        outputs.append(str(write_daily_workbook(day_rows, target, metrics)))
    persistence = None
    if db_path:
        connection = sqlite3.connect(str(db_path))
        try:
            persistence = persist_rows(connection, rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    pairs = pair_rows(rows)
    return {"outputs": outputs, "parse_metrics": metrics, "persistence": persistence,
            "logical_groups": len(pairs), "paired_value_mismatches": sum(item["type"] == "PAIRED_MISMATCH" for item in pairs)}


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--persist-to-db", type=Path)
    parser.add_argument("--analysis-date")
    parser.add_argument("--cdcs-missing-in-cpp", type=Path)
    parser.add_argument("--cpp-missing-in-cdcs", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        if args.cdcs_missing_in_cpp or args.cpp_missing_in_cdcs:
            if not (args.cdcs_missing_in_cpp and args.cpp_missing_in_cdcs):
                raise ValueError("Provide both directional CSV overrides")
            config["csv_inputs"] = [
                {"comparisonDirection": "CDCS_missing_in_CPP",
                    "csvPath": str(args.cdcs_missing_in_cpp.resolve())},
                {"comparisonDirection": "CPP_missing_in_CDCS",
                    "csvPath": str(args.cpp_missing_in_cdcs.resolve())},
            ]
            temp = args.config.with_name(args.config.stem + ".runtime.json")
            temp.write_text(json.dumps(config), encoding="utf-8")
            result = run(temp, args.persist_to_db,
                         args.output, args.analysis_date)
            temp.unlink(missing_ok=True)
        else:
            result = run(args.config, args.persist_to_db,
                         args.output, args.analysis_date)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
