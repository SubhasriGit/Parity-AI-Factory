"""Ordered deterministic PM000003 KD classification with evidence gates."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Optional

try:
    from .cpp_analyst import rebuild_cpp_data
except ImportError:
    from cpp_analyst import rebuild_cpp_data

CDCS_ONLY = "CDCS_missing_in_CPP"
CPP_ONLY = "CPP_missing_in_CDCS"


@dataclass(frozen=True)
class Verdict:
    classification: str
    kd_code: Optional[str]
    confidence: float
    hypothesis: str
    supporting_evidence: dict
    missing_evidence: list


@dataclass(frozen=True)
class InputRow:
    row_id: int
    day: str
    direction: str
    store: str
    product: str
    deal: str
    price_type: str
    effective_date: str
    dealer: Decimal
    retail: Decimal
    casting: Decimal
    timestamp_utc: str

    @property
    def snapshot_day(self) -> str:
        return self.timestamp_utc[:10] or self.day


def dec(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", [table]).fetchone() is not None


def mf_groups(connection: sqlite3.Connection, row: InputRow) -> dict:
    table = f"mf_data_{row.store}"
    if not table_exists(connection, table):
        return {}
    rows = connection.execute(
        f"SELECT PRICE_NAME, DEAL_NUMBER, PRICE_TYPE, PRICE, EFFECTIVE_DATE FROM {table} WHERE PRODUCT_NUMBER=? AND snapshot_day=?",
        [row.product, row.snapshot_day],
    ).fetchall()
    groups = {}
    for price_name, deal, side, price, _effective in rows:
        groups.setdefault((price_name or "", str(deal or "").zfill(4)), {})[
            side] = dec(price)
    return groups


def cpp_sides(connection: sqlite3.Connection, row: InputRow) -> dict:
    name = "Promo" if row.price_type == "PROMO" else "Regular"
    deal = row.deal if row.price_type == "PROMO" else ""
    rows = connection.execute(
        "SELECT PRICE_TYPE, PRICE FROM cpp_data WHERE STORE_NUMBER=? AND PRODUCT_NUMBER=? AND PRICE_NAME=? AND DEAL_NUMBER=? AND SNAPSHOT_DAY=?",
        [row.store, row.product, name, deal, row.snapshot_day],
    ).fetchall()
    return {side: dec(price) for side, price in rows if side in ("RETAIL", "DEALER")}


def master_dates(connection: sqlite3.Connection, row: InputRow) -> list[str]:
    if row.price_type == "PROMO":
        query = "SELECT promoRetailPriceEffectiveDate, promoDealerPriceEffectiveDate FROM deal_price_master WHERE productNumber=? AND dealNumber=? AND CAST(promoRetailPrice AS REAL)=? AND CAST(promoDealerPrice AS REAL)=?"
        params = [row.product, row.deal, float(row.retail), float(row.dealer)]
    else:
        query = "SELECT regularRetailPriceEffectiveDate, regularDealerPriceEffectiveDate FROM regular_price_master WHERE productNumber=? AND CAST(regularRetailPrice AS REAL)=? AND CAST(regularDealerPrice AS REAL)=?"
        params = [row.product, float(row.retail), float(row.dealer)]
    found = []
    for pair in connection.execute(query, params).fetchall():
        found.extend(str(value)[:10] for value in pair if value)
    return sorted(set(found))


def promo_master_dates(connection: sqlite3.Connection, row: InputRow) -> list[str]:
    return sorted({str(value)[:10] for value, in connection.execute(
        "SELECT promoRetailPriceEffectiveDate FROM deal_price_master WHERE productNumber=? AND dealNumber=? AND promoRetailPriceEffectiveDate IS NOT NULL",
        [row.product, row.deal],
    )})


def staging_add_dates(connection: sqlite3.Connection, row: InputRow) -> list[str]:
    return sorted({str(value)[:10] for value, in connection.execute(
        "SELECT recCreationDateTime FROM staging_product_price WHERE eventType='ADD' AND productNumber=? AND dealNumber=? "
        "AND CAST(retailPrice AS REAL)=? AND CAST(dealerPrice AS REAL)=? AND retailPriceEffectiveDate=?",
        [row.product, row.deal, float(row.retail), float(
            row.dealer), row.effective_date],
    )})


def override_zones(connection: sqlite3.Connection, store: str) -> list[str]:
    return [str(zone) for zone, in connection.execute(
        "SELECT DISTINCT zoneNumber FROM zone_store_relation WHERE storeNumber=? AND zoneNumber NOT IN ('0','1','2')", [
            store]
    )]


def duplicate_effective_dates(connection: sqlite3.Connection, row: InputRow, price_name: str, deal: str, side: str, amount: Decimal) -> list[str]:
    table = f"mf_data_{row.store}"
    if not table_exists(connection, table):
        return []
    return [str(item)[:10] for item, in connection.execute(
        f"SELECT DISTINCT EFFECTIVE_DATE FROM {table} WHERE snapshot_day=? AND PRODUCT_NUMBER=? AND PRICE_NAME=? AND DEAL_NUMBER=? AND PRICE_TYPE=? AND CAST(PRICE AS REAL)=? AND EFFECTIVE_DATE IS NOT NULL",
        [row.snapshot_day, row.product, price_name, deal, side, float(amount)],
    )]


def verdict(classification: str, kd: Optional[str], confidence: float, hypothesis: str,
            evidence: Optional[dict] = None, missing: tuple = ()) -> Verdict:
    return Verdict(classification, kd, confidence, hypothesis, evidence or {}, list(missing))


class Context:
    def __init__(self, connection: sqlite3.Connection, rows: list[InputRow], analysis_date: date):
        self.connection = connection
        self.analysis_date = analysis_date
        self.tomorrow = analysis_date + timedelta(days=1)
        self.paired = {}
        grouped: Dict[tuple, list] = {}
        for row in rows:
            grouped.setdefault((row.store, row.product, row.price_type,
                               row.deal, row.effective_date), []).append(row)
        for members in grouped.values():
            left = [row for row in members if row.direction == CDCS_ONLY]
            right = [row for row in members if row.direction == CPP_ONLY]
            while left and right:
                first, second = left.pop(0), right.pop(0)
                self.paired[first.row_id] = second
                self.paired[second.row_id] = first
        self.by_store_product = {}
        for row in rows:
            self.by_store_product.setdefault(
                (row.store, row.product), []).append(row)


def kd7(row: InputRow, ctx: Context) -> Optional[Verdict]:
    if row.direction != CDCS_ONLY:
        return None
    dates = master_dates(ctx.connection, row)
    if not dates or row.effective_date in dates:
        return None
    price_name = "CorporatePromoPrices" if row.price_type == "PROMO" else "CorporateRegularPrice"
    deal = row.deal if row.price_type == "PROMO" else ""
    duplicates = {}
    for side, amount in (("DEALER", row.dealer), ("RETAIL", row.retail)):
        if amount > 0:
            found = duplicate_effective_dates(
                ctx.connection, row, price_name, deal, side, amount)
            if len(found) > 1:
                duplicates[side] = found
    if not duplicates:
        return None
    return verdict("IMS_DATA_ISSUE", "KD-7", 0.85, "Master price exists at a different date and IMS contains genuine duplicate effective dates.",
                   {"master_dates": dates, "duplicate_dates": duplicates})


def kd4(row: InputRow, ctx: Context) -> Optional[Verdict]:
    if row.direction != CDCS_ONLY or row.price_type != "PROMO" or row.effective_date != ctx.analysis_date.isoformat():
        return None
    dates = promo_master_dates(ctx.connection, row)
    if dates and all(value > ctx.tomorrow.isoformat() for value in dates):
        return verdict("EXPECTED", "KD-4", 0.90, "Future promo appeared early in IMS.", {"future_dates": dates})
    return None


def kd3(row: InputRow, ctx: Context) -> Optional[Verdict]:
    if row.price_type != "PROMO":
        return None
    yesterday = (ctx.analysis_date - timedelta(days=1)).isoformat()
    events = staging_add_dates(ctx.connection, row)
    if row.direction == CDCS_ONLY and row.effective_date == yesterday:
        if events or row.dealer == 0 or row.retail == 0:
            return verdict("EXPECTED", "KD-3", 0.85 if events else 0.70, "Promo cross-day timing pattern.", {"staging_add_dates": events})
    if row.direction == CPP_ONLY and ctx.analysis_date.isoformat() in events:
        return verdict("EXPECTED", "KD-3", 0.85, "CPP promo arrived after a matching same-day staging ADD.", {"staging_add_dates": events})
    return None


def kd1(row: InputRow, ctx: Context) -> Optional[Verdict]:
    one_dealer = row.dealer > 0 and row.retail == 0
    one_retail = row.retail > 0 and row.dealer == 0
    if row.direction == CDCS_ONLY and (one_dealer or one_retail):
        sides = cpp_sides(ctx.connection, row)
        if one_dealer and sides.get("DEALER") == row.dealer and "RETAIL" in sides:
            return verdict("EXPECTED", "KD-1", 0.85, "CDCS sent a dealer-only update while CPP holds both sides.", {"cpp_sides": {key: str(value) for key, value in sides.items()}})
        if one_retail and sides.get("RETAIL") == row.retail and "DEALER" in sides:
            return verdict("EXPECTED", "KD-1", 0.85, "CDCS sent a retail-only update while CPP holds both sides.", {"cpp_sides": {key: str(value) for key, value in sides.items()}})
    if row.direction == CPP_ONLY and row.dealer > 0 and row.retail > 0:
        for (name, deal), sides in mf_groups(ctx.connection, row).items():
            side_only = ("DEALER" in sides and "RETAIL" not in sides) or (
                "RETAIL" in sides and "DEALER" not in sides)
            if side_only and all(sides[side] == getattr(row, "dealer" if side == "DEALER" else "retail") for side in sides):
                return verdict("EXPECTED", "KD-1", 0.85, "CPP has both price sides while IMS/CDCS evidence is one-sided.", {"ims_price_name": name, "ims_deal": deal, "ims_sides": {key: str(value) for key, value in sides.items()}})
    return None


def kd5(row: InputRow, ctx: Context) -> Optional[Verdict]:
    if row.price_type != "PROMO" or row.row_id not in ctx.paired:
        return None
    zones = override_zones(ctx.connection, row.store)
    if len(zones) < 2:
        return None
    prices = set()
    for zone in zones:
        prices.update(ctx.connection.execute(
            "SELECT promoRetailPrice || '|' || promoDealerPrice FROM deal_price_master WHERE productNumber=? AND dealNumber=? AND zoneNumber=?",
            [row.product, row.deal, zone],
        ))
    if len(prices) >= 2:
        return verdict("IMS_DATA_ISSUE", "KD-5", 0.80, "Store maps to multiple override zones with distinct master prices.", {"zones": zones, "distinct_prices": [list(item) for item in prices]})
    return None


def kd9(row: InputRow, ctx: Context) -> Optional[Verdict]:
    peer = ctx.paired.get(row.row_id)
    zones = override_zones(ctx.connection, row.store)
    if row.price_type == "PROMO" and peer and zones and (row.dealer, row.retail) != (peer.dealer, peer.retail):
        return verdict("EXPECTED", "KD-9", 0.55, "Known discrepancy pattern: possible promo override deletion or national-zone fallback.", {"zones": zones}, ("priceChangeEvent", "zone-specific deletion history", "packet lineage"))
    return None


def kd6(row: InputRow, ctx: Context) -> Optional[Verdict]:
    if row.direction != CDCS_ONLY or row.price_type != "REGULAR":
        return None
    found = ctx.connection.execute(
        "SELECT 1 FROM regular_price_master WHERE productNumber=? AND regularRetailChangeType='Initial Price' AND regularDealerChangeType='Initial Price' LIMIT 1",
        [row.product],
    ).fetchone()
    if found:
        return verdict("EXPECTED", "KD-6", 0.85, "Both regular-master change types are Initial Price.", {"change_types": "Initial Price"})
    return None


def kd10(row: InputRow, ctx: Context) -> Optional[Verdict]:
    if row.direction != CPP_ONLY or row.price_type != "PROMO":
        return None
    for peer in ctx.by_store_product.get((row.store, row.product), []):
        if peer.direction == CDCS_ONLY and peer.price_type == "PROMO" and peer.deal == row.deal and (peer.dealer, peer.retail) == (row.dealer, row.retail) and peer.effective_date != row.effective_date:
            return verdict("EXPECTED", "KD-10", 0.78, "Known discrepancy pattern: CPP promo has the same amounts as IMS but a different effective date.", {"cpp_date": row.effective_date, "ims_date": peer.effective_date}, ("priceChangeEvent", "IMS update/application history"))
    return None


def raw_parity(row: InputRow, ctx: Context) -> Optional[Verdict]:
    for peer in ctx.by_store_product.get((row.store, row.product), []):
        if peer.direction == row.direction:
            continue
        if (peer.dealer, peer.retail) == (row.dealer, row.retail) and (peer.effective_date, peer.deal, peer.price_type) != (row.effective_date, row.deal, row.price_type):
            return verdict("POTENTIAL_ISSUE", None, 0.75, "Raw prices match across sources but key/date tagging differs.", {"peer_row_id": peer.row_id})
    return None


def raw_mismatch(row: InputRow, ctx: Context) -> Optional[Verdict]:
    if row.direction != CPP_ONLY:
        return None
    sides = cpp_sides(ctx.connection, row)
    if len(sides) < 2:
        return None
    for peer in mf_groups(ctx.connection, row).values():
        if "DEALER" in peer and "RETAIL" in peer and (peer["DEALER"], peer["RETAIL"]) != (sides["DEALER"], sides["RETAIL"]):
            return verdict("EXPECTED", "KD-2", 0.70, "Known discrepancy pattern: same-day IMS and CPP rows exist but prices differ.", {"ims_sides": {key: str(value) for key, value in peer.items()}, "cpp_sides": {key: str(value) for key, value in sides.items()}}, ("priceChangeEvent",))
    return None


def kd2(row: InputRow, ctx: Context) -> Optional[Verdict]:
    if row.direction == CDCS_ONLY and not master_dates(ctx.connection, row):
        return verdict("EXPECTED", "KD-2", 0.45, "Known discrepancy pattern: CDCS row has no matching CPP master price.", {}, ("priceChangeEvent",))
    return None


def kd8(row: InputRow, _ctx: Context) -> Optional[Verdict]:
    if row.direction == CDCS_ONLY and row.price_type == "PROMO":
        return verdict("EXPECTED", "KD-8", 0.40, "Known discrepancy pattern: product/deal/store participation evidence is unavailable.", {}, ("product_deal_store_rel",))
    return None


PREDICATE_ORDER = (
    ("KD-7", kd7), ("KD-4", kd4), ("KD-3", kd3), ("KD-1", kd1),
    ("KD-5", kd5), ("KD-9", kd9), ("KD-6", kd6), ("KD-10", kd10),
    ("RAW_PARITY", raw_parity), ("RAW_MISMATCH_SAME_DAY", raw_mismatch),
    ("KD-2", kd2), ("KD-8", kd8),
)


def load_rows(connection: sqlite3.Connection) -> list[InputRow]:
    rows = []
    for raw in connection.execute("SELECT row_id,day,direction,store,offering_number,deal_number,price_type,effective_date,dealer_cost_price,retail_price,casting_price,timestamp_utc FROM mismatch_input ORDER BY row_id"):
        rows.append(InputRow(int(raw[0]), raw[1], raw[2], raw[3], raw[4], raw[5], raw[6], raw[7], dec(
            raw[8]), dec(raw[9]), dec(raw[10]), raw[11]))
    return rows


def resolve_analysis_date(connection: sqlite3.Connection, override: Optional[str] = None) -> date:
    if override:
        return date.fromisoformat(override)
    metadata = connection.execute(
        "SELECT value FROM _metadata WHERE key='mismatch_input.analysisDate'").fetchone()
    if metadata and metadata[0]:
        return date.fromisoformat(metadata[0])
    timestamps = [row[0] for row in connection.execute(
        "SELECT timestamp_utc FROM mismatch_input ORDER BY timestamp_utc DESC LIMIT 1")]
    if not timestamps:
        raise ValueError(
            "Cannot resolve analysis date; no mismatch rows or override")
    return date.fromisoformat(str(timestamps[0])[:10])


def classify_row(row: InputRow, ctx: Context) -> Verdict:
    for _, predicate in PREDICATE_ORDER:
        found = predicate(row, ctx)
        if found:
            return found
    return verdict("POTENTIAL_ISSUE", None, 0.20, "No deterministic predicate matched.", {}, ("priceChangeEvent", "product_deal_store_rel"))


def classify_all(connection: sqlite3.Connection, analysis_date: Optional[str] = None) -> dict:
    resolved_date = resolve_analysis_date(connection, analysis_date)
    rebuild_cpp_data(connection)
    rows = load_rows(connection)
    ctx = Context(connection, rows, resolved_date)
    distribution = {}
    connection.execute("DELETE FROM mismatch_verdict")
    payload = []
    for row in rows:
        result = classify_row(row, ctx)
        label = f"{result.classification}/{result.kd_code or '-'}"
        distribution[label] = distribution.get(label, 0) + 1
        payload.append((row.row_id, result.classification, result.kd_code, result.confidence, result.hypothesis,
                        json.dumps(result.supporting_evidence, sort_keys=True), json.dumps(result.missing_evidence)))
    connection.executemany(
        "INSERT INTO mismatch_verdict(row_id,classification,kd_code,confidence,hypothesis,supporting_evidence,missing_evidence) VALUES (?,?,?,?,?,?,?)",
        payload,
    )
    connection.commit()
    return {"analysis_date": resolved_date.isoformat(), "classified_rows": len(rows), "distribution": dict(sorted(distribution.items()))}


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--db", type=Path, required=True)
    run_parser.add_argument("--analysis-date")
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    try:
        connection = sqlite3.connect(str(args.db.resolve()))
        try:
            print(json.dumps(classify_all(connection, args.analysis_date), indent=2))
        finally:
            connection.close()
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
