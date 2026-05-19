from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

import pandas as pd

from app.testpacks import get_pack_class


@dataclass
class CellValidationResult:
    fail_count: int
    failed_tests: list[str]
    comment: str
    color: str


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return False


def _is_date(value: Any) -> bool:
    if isinstance(value, datetime):
        return True
    if isinstance(value, str):
        accepted_formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]
        for fmt in accepted_formats:
            try:
                datetime.strptime(value, fmt)
                return True
            except ValueError:
                continue
    return False


def _coerce_number(value: Any) -> float | None:
    if _is_number(value):
        return float(value)
    return None


def _severity_color(fail_count: int, max_failures: int) -> str:
    """Heatmap color gradient: light green (0 failures) → dark red (8+ failures)."""
    start_red, start_green, start_blue = (226, 240, 217)
    end_red, end_green, end_blue = (192, 0, 0)
    fail_scale_cap = 8

    _max_failures = max_failures
    _ = _max_failures
    clamped_fails = max(0.0, min(float(fail_scale_cap), float(fail_count)))
    ratio = clamped_fails / float(fail_scale_cap)

    red = int(start_red + (end_red - start_red) * ratio)
    green = int(start_green + (end_green - start_green) * ratio)
    blue = int(start_blue + (end_blue - start_blue) * ratio)
    return f"#{red:02X}{green:02X}{blue:02X}"


def validate_cell(value: Any, tests: list[dict[str, Any]]) -> CellValidationResult:
    failed_tests: list[str] = []

    for test in tests:
        name = test.get("name")

        if name == "required":
            if _is_empty(value):
                failed_tests.append("Value is required")

        elif name == "type":
            expected = test.get("expected")
            if expected == "number" and not _is_empty(value) and not _is_number(value):
                failed_tests.append("Expected a numeric value")
            elif expected == "date" and not _is_empty(value) and not _is_date(value):
                failed_tests.append("Expected a date value")
            elif expected == "text" and not _is_empty(value) and not isinstance(value, str):
                failed_tests.append("Expected a text value")

        elif name == "min":
            threshold = test.get("value")
            numeric_value = _coerce_number(value)
            if numeric_value is not None and threshold is not None and numeric_value < float(threshold):
                failed_tests.append(f"Must be >= {threshold}")

        elif name == "max":
            threshold = test.get("value")
            numeric_value = _coerce_number(value)
            if numeric_value is not None and threshold is not None and numeric_value > float(threshold):
                failed_tests.append(f"Must be <= {threshold}")

        elif name == "regex":
            pattern = test.get("pattern")
            if pattern and not _is_empty(value):
                if not re.match(pattern, str(value)):
                    failed_tests.append("Value format is invalid")

        elif name == "allowed_values":
            allowed = test.get("values", [])
            if not _is_empty(value) and value not in allowed:
                failed_tests.append("Value is not in the allowed set")

    fail_count = len(failed_tests)
    comment = "Passed all tests" if fail_count == 0 else "; ".join(failed_tests)

    return CellValidationResult(
        fail_count=fail_count,
        failed_tests=failed_tests,
        comment=comment,
        color=_severity_color(fail_count, max_failures=max(1, len(tests))),
    )


def validate_grid(
    addresses: list[list[str]],
    values: list[list[Any]],
    column_rules: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for row_index, row in enumerate(values):
        for col_index, value in enumerate(row):
            address = addresses[row_index][col_index]
            tests = column_rules.get(str(col_index), [])
            result = validate_cell(value=value, tests=tests)

            results.append(
                {
                    "address": address,
                    "rowIndex": row_index,
                    "columnIndex": col_index,
                    "value": value,
                    "failCount": result.fail_count,
                    "failedTests": result.failed_tests,
                    "comment": result.comment,
                    "color": result.color,
                }
            )

    return results


def validate_grid_with_packs(
    addresses: list[list[str]],
    values: list[list[Any]],
    column_rules: dict[str, list[dict[str, Any]]],
    test_packs: list[str],
    has_header_row: bool,
    pack_configs: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    report = validate_grid_with_packs_report(
        addresses=addresses,
        values=values,
        column_rules=column_rules,
        test_packs=test_packs,
        has_header_row=has_header_row,
        pack_configs=pack_configs,
    )
    return report["results"]


def validate_grid_with_packs_report(
    addresses: list[list[str]],
    values: list[list[Any]],
    column_rules: dict[str, list[dict[str, Any]]],
    test_packs: list[str],
    has_header_row: bool,
    pack_configs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not values:
        return {
            "results": [],
            "coverage": {
                "summary": {"totalDataRows": 0, "totalCells": 0, "failedCells": 0, "passedCells": 0},
                "packs": {},
            },
        }

    base_failures: dict[tuple[int, int], list[str]] = {}
    row_count = len(values)
    col_count = max((len(row) for row in values), default=0)

    # Track both failure messages and severity scores per cell
    base_failures: dict[tuple[int, int], list[str]] = {}
    severity_scores: dict[tuple[int, int], int] = {}

    for row_index in range(row_count):
        for col_index in range(col_count):
            base_failures[(row_index, col_index)] = []
            severity_scores[(row_index, col_index)] = 0

    for row_index, row in enumerate(values):
        for col_index, value in enumerate(row):
            tests = column_rules.get(str(col_index), [])
            if tests:
                base_result = validate_cell(value=value, tests=tests)
                if base_result.fail_count > 0:
                    base_failures[(row_index, col_index)].extend(base_result.failed_tests)
                    # Column rules default to ERROR severity (weight 3)
                    severity_scores[(row_index, col_index)] += base_result.fail_count * 3

    coverage_packs: dict[str, Any] = {}

    if test_packs:
        if not has_header_row:
            raise ValueError("test packs require hasHeaderRow=true so columns can be identified")
        if len(values) < 2:
            raise ValueError("test packs require at least one header row and one data row")

        headers = [str(value).strip() for value in values[0]]
        data_values = values[1:]

        data_frame = pd.DataFrame(data_values, columns=headers)
        header_to_col_index = {header: index for index, header in enumerate(headers)}

        pack_configs = pack_configs or {}

        for pack_name in test_packs:
            pack_class = get_pack_class(pack_name)
            if pack_class is None:
                coverage_packs[pack_name] = {
                    "tests": {},
                    "totals": {
                        "evaluatedRows": 0,
                        "failedRows": 0,
                        "passedRows": 0,
                        "testsRun": 0,
                    },
                    "warning": "Unknown pack",
                }
                continue

            pack_config = pack_configs.get(pack_name, {})

            configured_ref = pack_config.get("RefColumn") or pack_config.get("UTIColumn")
            if configured_ref is not None:
                trans_ref_column = str(configured_ref)
            else:
                trans_ref_candidates = [
                    "policy_id",
                    "policy_reference",
                    "ref",
                    "reference",
                ]
                trans_ref_column = next((name for name in trans_ref_candidates if name in data_frame.columns), "")

            if trans_ref_column not in data_frame.columns:
                coverage_packs[pack_name] = {
                    "tests": {},
                    "totals": {
                        "evaluatedRows": 0,
                        "failedRows": 0,
                        "passedRows": 0,
                        "testsRun": 0,
                    },
                    "warning": f"Missing RefColumn '{trans_ref_column}'",
                }
                continue

            enabled_tests_raw = pack_config.get("enabledTests")
            enabled_tests: list[str] | None = None
            if isinstance(enabled_tests_raw, list):
                selected = [str(item).strip() for item in enabled_tests_raw if str(item).strip()]
                enabled_tests = selected if selected else None

            pack = pack_class(df=data_frame, trans_ref=trans_ref_column, enabled_tests=enabled_tests)
            failures, pack_coverage = pack.run_with_coverage()

            tests_coverage: dict[str, Any] = {}
            evaluated_total = 0
            failed_total = 0
            passed_total = 0

            for test_cov in pack_coverage:
                tests_coverage[test_cov.test_name] = {
                    "targetColumns": test_cov.target_columns,
                    "description": test_cov.description,
                    "severity": test_cov.severity.name,
                    "severityWeight": int(test_cov.severity),
                    "evaluatedRows": test_cov.evaluated_rows,
                    "failedRows": test_cov.failed_rows,
                    "passedRows": test_cov.passed_rows,
                }
                evaluated_total += test_cov.evaluated_rows
                failed_total += test_cov.failed_rows
                passed_total += test_cov.passed_rows

            coverage_packs[pack_name] = {
                "tests": tests_coverage,
                "totals": {
                    "evaluatedRows": evaluated_total,
                    "failedRows": failed_total,
                    "passedRows": passed_total,
                    "testsRun": len(pack_coverage),
                },
            }

            for failure in failures:
                target_columns = failure.target_columns
                severity_weight = int(failure.severity)
                
                # Format: test ID (without "test_" prefix) + severity + docstring
                test_id = failure.test_name.replace("test_", "")
                severity_label = failure.severity.name
                failed_message = f"[{severity_label}] {test_id}: {failure.description}"

                matching_rows = data_frame[data_frame[trans_ref_column].astype(str).isin(failure.failed_refs)]
                
                # Apply failure to all target columns
                for target_column in target_columns:
                    if target_column not in header_to_col_index:
                        continue

                    target_col_index = header_to_col_index[target_column]
                    
                    for df_row_index in matching_rows.index.tolist():
                        sheet_row_index = int(df_row_index) + 1
                        base_failures[(sheet_row_index, target_col_index)].append(failed_message)
                        severity_scores[(sheet_row_index, target_col_index)] += severity_weight

    # Use severity score for heatmap instead of simple failure count
    max_severity_score = max((score for score in severity_scores.values()), default=1)
    results: list[dict[str, Any]] = []

    for row_index, row in enumerate(values):
        for col_index, value in enumerate(row):
            reasons = base_failures[(row_index, col_index)]
            fail_count = len(reasons)
            severity_score = severity_scores[(row_index, col_index)]
            # Join failures with double newline for blank line separation
            comment = "Passed all tests" if fail_count == 0 else "\n\n".join(reasons)
            results.append(
                {
                    "address": addresses[row_index][col_index],
                    "rowIndex": row_index,
                    "columnIndex": col_index,
                    "value": value,
                    "failCount": fail_count,
                    "severityScore": severity_score,
                    "failedTests": reasons,
                    "comment": comment,
                    "color": _severity_color(severity_score, max_failures=max(1, max_severity_score)),
                }
            )

    failed_cells = sum(1 for item in results if item["failCount"] > 0)
    total_cells = len(results)
    coverage = {
        "summary": {
            "totalDataRows": max(0, len(values) - (1 if has_header_row else 0)),
            "totalCells": total_cells,
            "failedCells": failed_cells,
            "passedCells": max(0, total_cells - failed_cells),
        },
        "packs": coverage_packs,
    }

    return {"results": results, "coverage": coverage}
