from __future__ import annotations

import argparse
from pathlib import Path
import sys
import zipfile

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pandas as pd
from openpyxl import load_workbook
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import PatternFill

from app.validation import validate_grid_with_packs_report


def heatmap_color(fail_count: int, max_failures: int) -> str:
    _max_failures = max_failures
    _ = _max_failures

    score = float(fail_count)
    if score <= 0:
        return "FFFFFF"

    level = int(max(1.0, min(10.0, score)))

    start_red, start_green, start_blue = (255, 235, 238)
    end_red, end_green, end_blue = (139, 0, 0)
    ratio = (level - 1) / 9

    red = int(start_red + (end_red - start_red) * ratio)
    green = int(start_green + (end_green - start_green) * ratio)
    blue = int(start_blue + (end_blue - start_blue) * ratio)
    return f"{red:02X}{green:02X}{blue:02X}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run test packs on an XLSX sheet and apply highlighting/comments.")
    parser.add_argument("--input", required=True, help="Path to input .xlsx")
    parser.add_argument("--output", required=False, help="Path to output .xlsx (defaults to input stem + _highlighted.xlsx)")
    parser.add_argument("--sheet", required=False, help="Worksheet name (defaults to active sheet)")
    parser.add_argument("--pack", action="append", default=["bordereaux"], help="Pack name to run. Can be repeated.")
    parser.add_argument("--ref-column", default="policy_reference", help="Reference column for pack config")
    return parser.parse_args()


def apply_highlighting(
    input_path: Path,
    output_path: Path,
    sheet_name: str | None,
    packs: list[str],
    trans_ref_column: str,
) -> dict[str, int]:
    try:
        workbook = load_workbook(input_path)
        worksheet = workbook[sheet_name] if sheet_name else workbook.active
    except (zipfile.BadZipFile, ValueError):
        frame = pd.read_csv(input_path, low_memory=False)
        workbook = Workbook()
        worksheet = workbook.active
        if sheet_name:
            worksheet.title = sheet_name

        worksheet.append(frame.columns.tolist())
        for row in frame.astype(object).where(pd.notnull(frame), None).values.tolist():
            worksheet.append(row)

    max_row = worksheet.max_row
    max_col = worksheet.max_column

    values: list[list[object | None]] = []
    addresses: list[list[str]] = []

    for row in range(1, max_row + 1):
        value_row: list[object | None] = []
        address_row: list[str] = []
        for col in range(1, max_col + 1):
            cell = worksheet.cell(row=row, column=col)
            value_row.append(cell.value)
            address_row.append(cell.coordinate)
        values.append(value_row)
        addresses.append(address_row)

    report = validate_grid_with_packs_report(
        addresses=addresses,
        values=values,
        column_rules={},
        test_packs=packs,
        has_header_row=True,
        pack_configs={"bordereaux": {"ID": trans_ref_column}},
    )

    highlighted = 0
    heatmapped = 0
    commented = 0

    # Use severity score for heatmap coloring
    max_severity_score = max((item.get("severityScore", item["failCount"]) for item in report["results"]), default=0)

    for result in report["results"]:
        cell = worksheet[result["address"]]
        if result["rowIndex"] == 0:
            cell.fill = PatternFill(fill_type=None)
            cell.comment = None
            continue

        severity_score = result.get("severityScore", result["failCount"])
        hex_color = heatmap_color(severity_score, max_severity_score)
        cell.fill = PatternFill(fill_type="solid", start_color=hex_color, end_color=hex_color)
        heatmapped += 1

        if result["failCount"] > 0:
            cell.comment = Comment(result["comment"], "validator")
            highlighted += 1
            commented += 1
        else:
            cell.comment = None

    workbook.save(output_path)

    return {
        "highlighted": highlighted,
        "heatmapped": heatmapped,
        "commented": commented,
        "failedCells": report["coverage"]["summary"]["failedCells"],
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else input_path.with_name(f"{input_path.stem}_highlighted.xlsx")
    )

    selected_packs = [pack for pack in args.pack if pack]
    if not selected_packs:
        selected_packs = ["bordereaux"]

    result = apply_highlighting(
        input_path=input_path,
        output_path=output_path,
        sheet_name=args.sheet,
        packs=selected_packs,
        trans_ref_column=args.ref_column,
    )

    print(f"output={output_path}")
    print(f"heatmapped={result['heatmapped']}")
    print(f"highlighted={result['highlighted']}")
    print(f"commented={result['commented']}")
    print(f"failedCells={result['failedCells']}")


if __name__ == "__main__":
    main()
