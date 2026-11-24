"""Generate a fully synthetic PM000003 run with unrelated identifiers and prices."""

from __future__ import annotations

import csv
import json
import random
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
STORES = ["5101", "5202", "5303", "5404", "5505"]
PRODUCTS = [f"{7001000 + index:07d}" for index in range(20)]
DEALS = ["7101", "7102", "7103"]
BASE_DATE = date(2026, 11, 16)
DAYS = [(BASE_DATE + timedelta(days=index)) for index in range(5)]


def write_csv(path: Path, headers: Iterable[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers))
        writer.writeheader()
        writer.writerows(rows)


def price_for(product: str, store: str, offset: float = 0.0) -> tuple[str, str]:
    seed = int(product) % 97 + int(store) % 11
    retail = round(20.0 + seed / 10 + offset, 2)
    dealer = round(retail * 0.82, 3)
    return f"{dealer:.3f}", f"{retail:.3f}"


def generate_cpp_files(output_dir: Path) -> dict[str, list[dict]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_rows, deal_rows, regular_rows, zone_rows, staging_rows = [], [], [], [], []
    packet_id = 100000
    for store_index, store in enumerate(STORES):
        zone_rows.append({"storeNumber": store, "zoneNumber": str(
            900 + store_index), "recCreationDateTime": "2026-11-20 08:00:00"})
        for product_index, product in enumerate(PRODUCTS):
            dealer, retail = price_for(product, store)
            packet_id += 1
            packet_rows.append({
                "packetId": str(packet_id),
                "storeNumber": store,
                "header": "{}",
                "body": json.dumps([{
                    "productNumber": product,
                    "corporateRegularPrice": [
                        {"type": "RETAIL", "price": retail, "priceEffectiveDate": DAYS[0].isoformat(
                        ), "changeType": "Initial Price"},
                        {"type": "DEALER", "price": dealer, "priceEffectiveDate": DAYS[0].isoformat(
                        ), "changeType": "Initial Price"},
                    ],
                    "corporatePromoPrice": [],
                    "coreCharges": [],
                }]),
                "recCreationDateTime": f"{DAYS[4].isoformat()} 08:00:00",
                "lastModifiedDateTime": f"{DAYS[4].isoformat()} 08:05:00",
                "errorMessage": "",
                "isProcessed": "1",
            })
            regular_rows.append({
                "regProductPriceId": str(1000000 + store_index * 1000 + product_index),
                "productNumber": product, "zoneNumber": str(900 + store_index), "zoneType": "OVERRIDE",
                "regularRetailPrice": retail, "regularRetailPriceEffectiveDate": DAYS[0].isoformat(), "regularRetailPriceEndDate": "",
                "regularDealerPrice": dealer, "regularDealerPriceEffectiveDate": DAYS[0].isoformat(), "regularDealerPriceEndDate": "",
                "lastModifiedDateTime": "2026-11-20 08:05:00", "recCreationDateTime": "2026-11-16 08:00:00",
                "regularRetailChangeType": "Initial Price" if product_index < 2 else "Update",
                "regularDealerChangeType": "Initial Price" if product_index < 2 else "Update",
            })
            for deal_index, deal in enumerate(DEALS):
                deal_dealer, deal_retail = price_for(
                    product, store, offset=deal_index + 0.75)
                deal_rows.append({
                    "promoProductPriceId": str(2000000 + store_index * 10000 + product_index * 10 + deal_index),
                    "productNumber": product, "zoneNumber": str(900 + store_index), "zoneType": "OVERRIDE",
                    "dealNumber": deal, "dealYear": "2026", "dealType": "SYNTHETIC_PROMO",
                    "promoRetailPrice": deal_retail, "promoRetailPriceEffectiveDate": (DAYS[1] + timedelta(days=deal_index)).isoformat(),
                    "promoDealerPrice": deal_dealer, "promoDealerPriceEffectiveDate": (DAYS[1] + timedelta(days=deal_index)).isoformat(),
                    "lastModifiedDateTime": "2026-11-20 08:05:00", "recCreationDateTime": "2026-11-16 08:00:00",
                    "promoRetailPriceEndDate": "", "promoDealerPriceEndDate": "",
                })
                event_id = f"EVT-{store_index:02d}-{product_index:02d}-{deal_index:02d}"
                staging_rows.append({
                    "eventId": event_id, "eventType": "ADD", "productNumber": product,
                    "zoneNumber": str(900 + store_index), "zoneType": "OVERRIDE", "eventAction": "CREATE",
                    "dealNumber": deal, "dealYear": "2026", "dealType": "SYNTHETIC_PROMO",
                    "retailPrice": deal_retail, "retailPriceEffectiveDate": (DAYS[1] + timedelta(days=deal_index)).isoformat(), "retailPriceEndDate": "",
                    "dealerPrice": deal_dealer, "dealerPriceEffectiveDate": (DAYS[1] + timedelta(days=deal_index)).isoformat(), "dealerPriceEndDate": "",
                    "rawRecCreationDateTime": "2026-11-16 09:00:00", "recCreationDateTime": "2026-11-16 09:00:00",
                    "retailChangeType": "ADD", "dealerChangeType": "ADD",
                })

    write_csv(output_dir / "corpPricePackets.csv",
              packet_rows[0].keys(), packet_rows)
    write_csv(output_dir / "dealPriceMaster.csv",
              deal_rows[0].keys(), deal_rows)
    write_csv(output_dir / "regularPriceMaster.csv",
              regular_rows[0].keys(), regular_rows)
    write_csv(output_dir / "zoneStoreRelation.csv",
              zone_rows[0].keys(), zone_rows)
    write_csv(output_dir / "stagingProductPrice.csv",
              staging_rows[0].keys(), staging_rows)
    return {"packets": packet_rows, "deals": deal_rows, "regular": regular_rows, "zones": zone_rows, "staging": staging_rows}


def generate_ims_source(path: Path, cpp: dict[str, list[dict]]) -> tuple[list[dict], list[dict]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(str(path))
    mappings = []
    metadata_rows = []
    for store in STORES:
        table = f"ims_source_{store}"
        connection.execute(f'''CREATE TABLE "{table}" (
            STORE_ID TEXT, PRODUCT_NUMBER TEXT, PRICE_NAME TEXT, PRICE_TYPE TEXT,
            DEAL_NUMBER TEXT, PRICE TEXT, EFFECTIVE_DATE TEXT, Comment TEXT)''')
        rows = []
        for item in cpp["regular"]:
            if item["productNumber"] not in PRODUCTS[:12]:
                continue
            rows.append((store, item["productNumber"], "CorporateRegularPrice", "RETAIL", "",
                        item["regularRetailPrice"], item["regularRetailPriceEffectiveDate"], "synthetic"))
            rows.append((store, item["productNumber"], "CorporateRegularPrice", "DEALER", "",
                        item["regularDealerPrice"], item["regularDealerPriceEffectiveDate"], "synthetic"))
        for item in cpp["deals"]:
            if item["productNumber"] not in PRODUCTS[:8] or item["zoneNumber"] != str(900 + STORES.index(store)):
                continue
            rows.append((store, item["productNumber"], "CorporatePromoPrices", "RETAIL", item["dealNumber"],
                        item["promoRetailPrice"], item["promoRetailPriceEffectiveDate"], "synthetic"))
            rows.append((store, item["productNumber"], "CorporatePromoPrices", "DEALER", item["dealNumber"],
                        item["promoDealerPrice"], item["promoDealerPriceEffectiveDate"], "synthetic"))
        connection.executemany(
            f'INSERT INTO "{table}" VALUES (?,?,?,?,?,?,?,?)', rows)
        mappings.append({"source_table": table, "store": store,
                        "snapshot_day": DAYS[4].isoformat()})
        metadata_rows.extend(rows)
    connection.commit()
    connection.close()
    (path.parent / "day-map.json").write_text(json.dumps(
        {"mappings": mappings}, indent=2), encoding="utf-8")
    return mappings, metadata_rows


def dto(product: str, deal: str, day: date, dealer: str, retail: str) -> str:
    return f"PromoDealPriceDto(dealNumber={int(deal) if deal else 0}, offeringNumber={int(product)}, effectiveDate={day.isoformat()}, dealerCostPrice={dealer}, retailPrice={retail}, castingPrice=0)"


def generate_mismatch_csvs(input_dir: Path, cpp: dict[str, list[dict]]) -> tuple[list[dict], list[dict]]:
    input_dir.mkdir(parents=True, exist_ok=True)
    cdcs_rows, cpp_rows = [], []
    for day_index, run_day in enumerate(DAYS):
        for store_index, store in enumerate(STORES):
            regular_by_product = {
                row["productNumber"]: row for row in cpp["regular"] if row["zoneNumber"] == str(900 + store_index)}
            deals_by_product = {}
            for row in cpp["deals"]:
                if row["zoneNumber"] == str(900 + store_index):
                    deals_by_product.setdefault(
                        row["productNumber"], []).append(row)

            cdcs_dtos, cpp_dtos = [], []
            # KD-1: one-sided CDCS rows with both-side CPP evidence.
            for product in PRODUCTS[day_index:day_index+2]:
                row = regular_by_product[product]
                cdcs_dtos.append(dto(product, "0000", run_day,
                                 "0.000", row["regularRetailPrice"]))
            # KD-6: regular CDCS-only initial-price rows.
            product = PRODUCTS[day_index % 2]
            row = regular_by_product[product]
            cdcs_dtos.append(dto(product, "0000", run_day,
                             row["regularDealerPrice"], row["regularRetailPrice"]))
            # KD-2: regular CDCS-only row with no matching master price.
            product = PRODUCTS[15 + day_index]
            cdcs_dtos.append(dto(product, "0000", run_day, "11.111", "19.999"))
            # KD-8: promo known pattern, missing deal/store participation source.
            product = PRODUCTS[2 + day_index]
            promo = deals_by_product[product][0]
            cdcs_dtos.append(dto(
                product, promo["dealNumber"], run_day, promo["promoDealerPrice"], promo["promoRetailPrice"]))
            # KD-10: same promo amounts, different effective date, CPP-only.
            product = PRODUCTS[7 + day_index]
            promo = deals_by_product[product][0]
            cdcs_dtos.append(dto(product, promo["dealNumber"], run_day - timedelta(
                days=1), promo["promoDealerPrice"], promo["promoRetailPrice"]))
            cpp_dtos.append(dto(
                product, promo["dealNumber"], run_day, promo["promoDealerPrice"], promo["promoRetailPrice"]))
            # KD-9: paired promo mismatch in a known single-zone context.
            product = PRODUCTS[12 + day_index]
            promo = deals_by_product[product][0]
            cdcs_dtos.append(dto(
                product, promo["dealNumber"], run_day, promo["promoDealerPrice"], promo["promoRetailPrice"]))
            cpp_dtos.append(dto(product, promo["dealNumber"], run_day, str(
                round(float(promo["promoDealerPrice"]) + 1.0, 3)), promo["promoRetailPrice"]))
            # Uncoded potential issue: regular record with matching master values.
            product = PRODUCTS[18]
            row = regular_by_product[product]
            cpp_dtos.append(dto(product, "0000", run_day,
                            row["regularDealerPrice"], row["regularRetailPrice"]))

            cdcs_rows.append({
                "Timestamp": (datetime.combine(run_day, datetime.min.time()) + timedelta(hours=10)).strftime("%B %d, %Y %H:%M:%S"),
                "Store": store, "Message": "CDCS_MIGRATION: synthetic CDCS-only records: [" + ", ".join(cdcs_dtos) + "]",
                "Message Id": f"SYN-CDCS-{day_index:02d}-{store}",
            })
            cpp_rows.append({
                "Timestamp": (datetime.combine(run_day, datetime.min.time()) + timedelta(hours=10, minutes=5)).strftime("%B %d, %Y %H:%M:%S"),
                "Store": store, "Message": "CDCS_MIGRATION: synthetic CPP-only records: [" + ", ".join(cpp_dtos) + "]",
                "Message Id": f"SYN-CPP-{day_index:02d}-{store}",
            })

    cdcs_path = input_dir / "Diff-mismatch-synthetic-CDCS-missing-in-CPP.csv"
    cpp_path = input_dir / "Diff-mismatch-synthetic-CPP-missing-in-CDCS.csv"
    headers = ["Timestamp", "Store", "Message", "Message Id"]
    write_csv(cdcs_path, headers, cdcs_rows)
    write_csv(cpp_path, headers, cpp_rows)
    return cdcs_rows, cpp_rows


def generate_config(cdcs_path: Path, cpp_path: Path) -> Path:
    config = {
        "csv_inputs": [
            {"comparisonDirection": "CDCS_missing_in_CPP",
                "csvPath": str(cdcs_path)},
            {"comparisonDirection": "CPP_missing_in_CDCS",
                "csvPath": str(cpp_path)},
        ],
        "parserPatternRegex": r"PromoDealPriceDto\(dealNumber=(?P<dealNumber>[^,)]*), offeringNumber=(?P<offeringNumber>[^,)]*), effectiveDate=(?P<effectiveDate>[^,)]*), dealerCostPrice=(?P<dealerCostPrice>[^,)]*), retailPrice=(?P<retailPrice>[^,)]*), castingPrice=(?P<castingPrice>[^)]*)\)",
        "priceTypeRules": [{"rule": "dealNumber != 0", "priceType": "PROMO"}, {"rule": "dealNumber = 0", "priceType": "REGULAR"}],
        "detailColumns": ["comparisonDirection", "store", "timestamp", "messageId", "priceType", "dealNumber", "offeringNumber", "effectiveDate", "dealerCostPrice", "retailPrice", "castingPrice", "sourceSummary"],
        "analysisColumns": ["comparisonDirection", "store", "timestamp", "priceType", "dealNumber", "offeringNumber", "effectiveDate", "dealerCostPrice", "retailPrice", "castingPrice", "possibleCause", "possibleCauseDetails", "classification", "kdCode"],
        "analysisSheetSuffix": "_analysis",
        "summaryMetrics": ["totalParsedRows", "uniqueRows", "regCount", "promoCount", "castingCount", "unknownCount", "rowsWithNonZeroRetailPrice"],
        "outputPath": str(ROOT / "reports" / "synthetic_pm000003_analysis.xlsx"),
    }
    path = ROOT / "config" / "synthetic-run.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def run(command: list[str]) -> None:
    completed = subprocess.run(
        [sys.executable, *command], cwd=str(ROOT), text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(
            f"Command failed ({' '.join(command)}):\n{completed.stdout}\n{completed.stderr}")
    print(completed.stdout.strip())


def main() -> int:
    backup_root = ROOT.parent / "Project1-Private-Originals"
    backup_root.mkdir(parents=True, exist_ok=True)
    for relative in ("input", "cpp_data", "ims_data", "reports", "output/backups"):
        source = ROOT / relative
        if source.exists() and (backup_root / relative).exists() is False:
            (backup_root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, backup_root / relative)
    original_db = ROOT / "pm000003_mf_packets_multi_store.db"
    if original_db.exists():
        backup_db = backup_root / original_db.name
        if not backup_db.exists():
            shutil.copy2(original_db, backup_db)

    for folder in (ROOT / "input", ROOT / "cpp_data", ROOT / "ims_data", ROOT / "output"):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for report in reports_dir.iterdir():
        if report.is_file() and report.suffix.lower() != ".pptx":
            report.unlink()

    synthetic_db = ROOT / "pm000003_mf_packets_multi_store.db"
    if synthetic_db.exists():
        synthetic_db.unlink()

    cpp = generate_cpp_files(ROOT / "cpp_data")
    generate_ims_source(ROOT / "ims_data" / "synthetic_source.db", cpp)
    cdcs_rows, cpp_rows = generate_mismatch_csvs(ROOT / "input", cpp)
    config = generate_config(ROOT / "input" / "Diff-mismatch-synthetic-CDCS-missing-in-CPP.csv",
                             ROOT / "input" / "Diff-mismatch-synthetic-CPP-missing-in-CDCS.csv")

    run(["scripts/init_database.py", "--db", str(synthetic_db)])
    run(["scripts/load_cpp_snapshot_to_db.py", "--db",
        str(synthetic_db), "--csv-dir", str(ROOT / "cpp_data"), "--keep-empty-bodies"])
    run(["scripts/migrate_ims_snapshot_to_db.py", "--source", str(ROOT / "ims_data" / "synthetic_source.db"),
        "--db", str(synthetic_db), "--day-map", str(ROOT / "ims_data" / "day-map.json")])
    run(["pm000003_mismatch_report.py", "--config",
        str(config), "--persist-to-db", str(synthetic_db)])
    run(["scripts/classify_kd.py", "run", "--db",
        str(synthetic_db), "--analysis-date", DAYS[-1].isoformat()])
    candidates_path = ROOT / "output" / "synthetic_llm_candidates.json"
    findings_path = ROOT / "output" / "synthetic_llm_findings.json"
    run(["scripts/llm_bridge.py", "export", "--db",
        str(synthetic_db), "--output", str(candidates_path)])
    candidate_data = json.loads(candidates_path.read_text(encoding="utf-8"))
    findings = [{
        "row_id": record["row_id"],
        "classification": "INSUFFICIENT_EVIDENCE",
        "kd_code": record["deterministic"]["kd_code"],
        "confidence": record["deterministic"]["confidence"],
        "hypothesis": "No additional synthetic evidence was supplied beyond the deterministic snapshot.",
        "supporting_evidence": {},
        "missing_evidence": record["deterministic"]["missing_evidence"],
        "confirmation_steps": ["Review the synthetic row and supporting evidence"],
    } for record in candidate_data["records"]]
    findings_path.write_text(json.dumps(
        {"schema_version": 1, "findings": findings}, indent=2), encoding="utf-8")
    run(["scripts/llm_bridge.py", "import", "--db",
        str(synthetic_db), "--file", str(findings_path)])
    run(["scripts/review_and_report.py", "report", "--db", str(synthetic_db),
        "--output", str(ROOT / "reports" / "synthetic_pm000003_analysis.xlsx")])
    run(["scripts/validate_outputs.py", "--db", str(synthetic_db),
        "--workbook", str(ROOT / "reports" / "synthetic_pm000003_analysis.xlsx")])
    print(json.dumps({
        "database": str(synthetic_db),
        "cpp_snapshot_rows": sum(len(rows) for rows in cpp.values()),
        "mismatch_log_rows": len(cdcs_rows) + len(cpp_rows),
        "report": str(ROOT / "reports" / "synthetic_pm000003_analysis.xlsx"),
        "private_originals": str(backup_root),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
