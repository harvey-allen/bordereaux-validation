from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook


ROOT = Path("/Users/harvey/Documents/Portfolio/axios/bordereaux-validation")
FIELD_CONFIG_DIR = ROOT / "backend" / "app" / "testpacks" / "field_configurations"
OUTPUT_PATH = ROOT / "data" / "sample_bordereaux_multisheet_submission.xlsx"
TARGET_TERRITORY = "UK"
ROW_COUNT = 10


def load_pack_columns(pack_name: str, territory: str) -> list[str]:
    config_path = FIELD_CONFIG_DIR / f"{pack_name}.json"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    territory_entry = raw.get(territory, {})

    columns: list[str] = []
    seen: set[str] = set()
    for group_name in ("mandatory", "conditional"):
        for item in territory_entry.get(group_name, []):
            field_name = str(item.get("field") or "").strip()
            if not field_name or field_name in seen:
                continue
            seen.add(field_name)
            columns.append(field_name)
    return columns


def sample_value(field_name: str, index: int, pack_name: str, base_date: date) -> object:
    normalized = field_name.lower()
    current_date = base_date + timedelta(days=index)

    if "date" in normalized:
        return current_date.isoformat()

    if "currency" in normalized:
        return "GBP"

    if "%" in field_name or "percentage" in normalized:
        return round(12.5 + (index * 0.2), 2)

    numeric_tokens = [
        "amount", "premium", "tax", "fee", "reserve", "incurred", "claim", "limit", "deductible", "exchange rate",
    ]
    if any(token in normalized for token in numeric_tokens):
        return round(1000 + (index * 137.75), 2)

    if any(token in normalized for token in ["country", "territory", "state of filing"]):
        return "UK"

    if any(token in normalized for token in ["postcode", "zip"]):
        return f"SW1A {index:02d}AA"

    if "status" in normalized:
        return "OPEN" if pack_name == "claims" and index % 3 else "CLOSED"

    if "type" in normalized:
        return "DIRECT"

    if "name" in normalized:
        return f"{field_name.split(' ')[0]} {index}"

    if any(token in normalized for token in ["ref", "reference", "number", "no"]):
        prefix = "CLM" if pack_name == "claims" else "POL"
        return f"{prefix}-{10000 + index}"

    if any(token in normalized for token in ["flag", "indicator"]):
        return "Y" if index % 2 == 0 else "N"

    return f"{field_name} {index}"


def build_sheet(wb: Workbook, pack_name: str, sheet_name: str, territory: str, source_file: str) -> None:
    columns = load_pack_columns(pack_name, territory)
    ws = wb.create_sheet(sheet_name)
    ws.append(columns)

    base_date = date(2026, 4, 1)
    for i in range(1, ROW_COUNT + 1):
        row = [sample_value(column, i, pack_name, base_date) for column in columns]
        ws.append(row)


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    wb.remove(wb.active)

    source_file = OUTPUT_PATH.name
    build_sheet(wb, "premium", "Premium_Submission_UK", TARGET_TERRITORY, source_file)
    build_sheet(wb, "claims", "Claims_Submission_UK", TARGET_TERRITORY, source_file)

    wb.save(OUTPUT_PATH)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
