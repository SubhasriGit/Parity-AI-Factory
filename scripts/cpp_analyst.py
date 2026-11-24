"""Deterministic CPP packet expansion and evidence preparation."""

from __future__ import annotations

import argparse
import json
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

TRUNCATED_LENGTHS = {65535, 1048576}


def pad(value, width: int) -> str:
    return str("" if value is None else value).strip().zfill(width) if value is not None else ""


def price_text(value) -> str:
    if value is None:
        return "0.000"
    try:
        return f"{Decimal(str(value)):.3f}"
    except (InvalidOperation, ValueError):
        return "0.000"


def explode_packet(store: str, snapshot_day: str, data) -> list[tuple]:
    rows = []
    if not isinstance(data, list):
        return rows
    for entry in data:
        if not isinstance(entry, dict):
            continue
        product = pad(entry.get("productNumber"), 7)
        for item in entry.get("corporateRegularPrice") or []:
            rows.append((pad(store, 4), product, "Regular", str(item.get("type") or "").upper(), "",
                         price_text(item.get("price")), item.get("priceEffectiveDate"), snapshot_day, item.get("changeType")))
        for item in entry.get("corporatePromoPrice") or []:
            rows.append((pad(store, 4), product, "Promo", str(item.get("type") or "").upper(),
                         pad(item.get("dealNumber"), 4), price_text(
                             item.get("price")),
                         item.get("dealerVisibilityDate"), snapshot_day,
                         f"dealYear={item.get('dealYear')};dealType={item.get('dealType')}"))
        for item in entry.get("coreCharges") or []:
            deal = item.get("dealNumber")
            rows.append((pad(store, 4), product, "CoreCharges", str(item.get("type") or "").upper(),
                         pad(deal, 4) if deal else "", price_text(
                             item.get("price")),
                         item.get("priceEffectiveDate") or item.get("dealerVisibilityDate"), snapshot_day, None))
    return rows


def rebuild_cpp_data(connection: sqlite3.Connection) -> dict:
    connection.execute("BEGIN")
    try:
        connection.execute("DELETE FROM cpp_data")
        inserted = 0
        malformed = []
        for packet_id, store, rec_created, body in connection.execute(
            "SELECT packetId, storeNumber, recCreationDateTime, body FROM cpp_price_packets "
            "WHERE body IS NOT NULL AND LENGTH(body) > 0 ORDER BY packetId"
        ):
            if len(body) in TRUNCATED_LENGTHS:
                malformed.append({"packetId": packet_id, "store": store, "body_length": len(
                    body), "reason": "suspected truncation"})
                continue
            try:
                data = json.loads(body)
            except json.JSONDecodeError as exc:
                malformed.append({"packetId": packet_id, "store": store, "body_length": len(
                    body), "reason": str(exc)})
                continue
            snapshot_day = str(rec_created)[:10] if rec_created else None
            rows = explode_packet(str(store), snapshot_day, data)
            if rows:
                connection.executemany(
                    "INSERT INTO cpp_data(STORE_NUMBER,PRODUCT_NUMBER,PRICE_NAME,PRICE_TYPE,DEAL_NUMBER,PRICE,EFFECTIVE_DATE,SNAPSHOT_DAY,Comment) VALUES (?,?,?,?,?,?,?,?,?)",
                    rows,
                )
                inserted += len(rows)
        now = datetime_utc_now()
        connection.execute(
            "INSERT INTO _metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("cpp_data.loadedAtUtc", now),
        )
        connection.execute(
            "INSERT INTO _metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("cpp_data.insertedRows", str(inserted)),
        )
        connection.commit()
        return {"inserted_rows": inserted, "malformed_packets": malformed, "table_total": inserted}
    except Exception:
        connection.rollback()
        raise


def datetime_utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(db_path: Path) -> dict:
    connection = sqlite3.connect(str(db_path))
    try:
        return rebuild_cpp_data(connection)
    finally:
        connection.close()


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    try:
        print(json.dumps(run(args.db.resolve()), indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
