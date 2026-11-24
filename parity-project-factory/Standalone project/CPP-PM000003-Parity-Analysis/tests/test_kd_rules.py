# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


init_database_module = load_module(
    "cpp_kd_init_database", ROOT / "scripts" / "init_database.py")
classify_module = load_module(
    "cpp_classify_kd", ROOT / "scripts" / "classify_kd.py")
initialize_database = init_database_module.initialize_database
classify_all = classify_module.classify_all
PREDICATE_ORDER = classify_module.PREDICATE_ORDER


def base_row(**overrides) -> tuple:
    values = {
        "day": "2026-08-14", "direction": "CDCS_missing_in_CPP", "store": "0035",
        "product": "0000001", "deal": "0001", "price_type": "PROMO",
        "effective": "2026-08-14", "dealer": "0.500", "retail": "1.000", "casting": "0.000",
        "timestamp": "2026-08-14 10:00:00", "message": "m1",
    }
    values.update(overrides)
    return tuple(values[key] for key in ("day", "direction", "store", "product", "deal", "price_type", "effective", "dealer", "retail", "casting", "timestamp", "message"))


def insert_rows(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    connection.executemany(
        "INSERT INTO mismatch_input(day,direction,store,offering_number,deal_number,price_type,effective_date,dealer_cost_price,retail_price,casting_price,timestamp_utc,message_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    connection.execute(
        "INSERT OR REPLACE INTO _metadata(key,value) VALUES('mismatch_input.analysisDate','2026-08-14')")
    connection.commit()


def test_predicate_order_is_exact() -> None:
    assert [name for name, _ in PREDICATE_ORDER] == [
        "KD-7", "KD-4", "KD-3", "KD-1", "KD-5", "KD-9",
        "KD-6", "KD-10", "RAW_PARITY", "RAW_MISMATCH_SAME_DAY", "KD-2", "KD-8",
    ]


def test_kd4_precedes_later_candidate_rules(tmp_path: Path) -> None:
    db = tmp_path / "kd4.db"
    initialize_database(db)
    connection = sqlite3.connect(str(db))
    insert_rows(connection, [base_row()])
    connection.execute(
        "INSERT INTO deal_price_master(promoProductPriceId,productNumber,dealNumber,promoRetailPriceEffectiveDate) VALUES (1,?,?,?)",
        ["0000001", "0001", "2026-08-20"],
    )
    connection.commit()

    result = classify_all(connection)
    stored = connection.execute(
        "SELECT classification,kd_code FROM mismatch_verdict").fetchone()
    connection.close()

    assert result["classified_rows"] == 1
    assert stored == ("EXPECTED", "KD-4")


def test_kd1_requires_both_side_cpp_evidence(tmp_path: Path) -> None:
    db = tmp_path / "kd1.db"
    initialize_database(db)
    connection = sqlite3.connect(str(db))
    insert_rows(connection, [base_row(dealer="0.500", retail="0")])
    connection.executemany(
        "INSERT INTO cpp_data(STORE_NUMBER,PRODUCT_NUMBER,PRICE_NAME,PRICE_TYPE,DEAL_NUMBER,PRICE,SNAPSHOT_DAY) VALUES (?,?,?,?,?,?,?)",
        [("0035", "0000001", "Promo", "DEALER", "0001", "0.500", "2026-08-14"),
         ("0035", "0000001", "Promo", "RETAIL", "0001", "1.000", "2026-08-14")],
    )
    connection.commit()

    result = classify_all(connection)
    stored = connection.execute(
        "SELECT classification,kd_code FROM mismatch_verdict").fetchone()
    connection.close()
    assert result["classified_rows"] == 1
    assert stored == ("EXPECTED", "KD-2")


def test_kd1_matches_packet_evidence_for_one_sided_cdcs_row(tmp_path: Path) -> None:
    db = tmp_path / "kd1-positive.db"
    initialize_database(db)
    connection = sqlite3.connect(str(db))
    insert_rows(connection, [base_row(dealer="0.500", retail="0")])
    body = json.dumps([{
        "productNumber": "1",
        "corporatePromoPrice": [
            {"type": "dealer", "price": 0.5, "dealerVisibilityDate": "2026-08-14",
                "dealNumber": 1, "dealYear": "2026", "dealType": "A"},
            {"type": "retail", "price": 1.0, "dealerVisibilityDate": "2026-08-14",
                "dealNumber": 1, "dealYear": "2026", "dealType": "A"},
        ],
    }])
    connection.execute(
        "INSERT INTO cpp_price_packets(packetId,storeNumber,body,recCreationDateTime) VALUES (?,?,?,?)",
        [1, "0035", body, "2026-08-14 10:00:00"],
    )
    connection.commit()

    classify_all(connection)
    stored = connection.execute(
        "SELECT classification,kd_code,supporting_evidence FROM mismatch_verdict").fetchone()
    connection.close()
    assert stored[:2] == ("EXPECTED", "KD-1")
    assert "cpp_sides" in json.loads(stored[2])


def test_kd6_and_missing_master_candidates_persist_one_verdict_each(tmp_path: Path) -> None:
    db = tmp_path / "mixed.db"
    initialize_database(db)
    connection = sqlite3.connect(str(db))
    insert_rows(connection, [
        base_row(deal="0000", price_type="REGULAR", product="0000001"),
        base_row(product="0000002", deal="0002"),
    ])
    connection.execute(
        "INSERT INTO regular_price_master(regProductPriceId,productNumber,regularRetailChangeType,regularDealerChangeType) VALUES(1,?,?,?)",
        ["0000001", "Initial Price", "Initial Price"],
    )
    connection.commit()

    result = classify_all(connection)
    verdicts = connection.execute(
        "SELECT row_id,classification,kd_code,missing_evidence FROM mismatch_verdict ORDER BY row_id").fetchall()
    row_count = connection.execute(
        "SELECT COUNT(*) FROM mismatch_input").fetchone()[0]
    connection.close()

    assert result["classified_rows"] == row_count == len(verdicts) == 2
    assert verdicts[0][2] == "KD-6"
    assert verdicts[1][1] == "EXPECTED"
    assert verdicts[1][2] == "KD-2"
    assert "priceChangeEvent" in json.loads(verdicts[1][3])
