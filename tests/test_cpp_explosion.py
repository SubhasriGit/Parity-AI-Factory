# pyright: reportMissingImports=false
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from init_database import initialize_database
from cpp_analyst import rebuild_cpp_data


def test_explodes_regular_promo_core_and_skips_malformed(tmp_path: Path) -> None:
    db = tmp_path / "analysis.db"
    initialize_database(db)
    body = json.dumps([{
        "productNumber": "1",
        "corporateRegularPrice": [{"type": "retail", "price": 1.2, "priceEffectiveDate": "2026-08-14", "changeType": "Initial Price"}],
        "corporatePromoPrice": [{"type": "dealer", "price": 0.5, "dealerVisibilityDate": "2026-08-15", "dealNumber": 2, "dealYear": "2026", "dealType": "A"}],
        "coreCharges": [{"type": "retail", "price": 0.1, "priceEffectiveDate": "2026-08-14"}],
    }])
    connection = sqlite3.connect(str(db))
    connection.executemany("INSERT INTO cpp_price_packets(packetId,storeNumber,body,recCreationDateTime) VALUES (?,?,?,?)", [
        (1, "35", body, "2026-08-14 10:00:00"),
        (2, "64", "not-json", "2026-08-14 10:00:00"),
    ])
    connection.commit()

    result = rebuild_cpp_data(connection)
    rows = connection.execute(
        "SELECT * FROM cpp_data ORDER BY PRICE_NAME").fetchall()
    connection.close()

    assert result["inserted_rows"] == 3
    assert len(result["malformed_packets"]) == 1
    assert {row[2] for row in rows} == {"Regular", "Promo", "CoreCharges"}
    assert {row[0] for row in rows} == {"0035"}
    assert {row[1] for row in rows} == {"0000001"}
    assert next(row for row in rows if row[2] == "Regular")[5] == "1.200"
    assert next(row for row in rows if row[2] == "Promo")[4] == "0002"
