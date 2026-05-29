from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
import re
from typing import Any, Callable

import pandas as pd

TEST_PACKS: dict[str, type["BaseTestPack"]] = {}


class Severity(IntEnum):
    """Severity levels for test failures, affecting heatmap intensity."""
    INFO = 0       # Informational only, no heatmap impact
    WARNING = 1    # Low impact on heatmap
    ERROR = 2      # Medium impact on heatmap
    CRITICAL = 3   # High impact on heatmap


@dataclass
class PackFailure:
    test_name: str
    test_code: str | None
    target_columns: list[str]
    failed_refs: set[str]
    description: str
    severity: Severity = Severity.ERROR


@dataclass
class PackTestCoverage:
    test_name: str
    test_code: str | None
    target_columns: list[str]
    description: str
    severity: Severity
    evaluated_rows: int
    failed_rows: int
    passed_rows: int


def register_pack(name: str) -> Callable[[type["BaseTestPack"]], type["BaseTestPack"]]:
    def decorator(pack_cls: type["BaseTestPack"]) -> type["BaseTestPack"]:
        TEST_PACKS[name.lower()] = pack_cls
        return pack_cls

    return decorator


def register_test(
    func: Callable[..., pd.DataFrame | None] | None = None,
    *,
    target_column: str | None = None,
    target_columns: list[str] | None = None,
    description: str | None = None,
    severity: Severity = Severity.ERROR,
) -> Callable[..., Any]:
    """
    Register a test method in a test pack.
    
    Args:
        target_column: Single column this test affects (for backwards compatibility)
        target_columns: List of columns this test affects (takes precedence over target_column)
        description: Human-readable description of what the test validates
        severity: Impact level - INFO (0), WARNING (1), ERROR (2), CRITICAL (3)
    """
    def decorator(test_func: Callable[..., pd.DataFrame | None]) -> Callable[..., pd.DataFrame | None]:
        setattr(test_func, "_is_registered_test", True)
        # Support both single column and multiple columns
        if target_columns:
            setattr(test_func, "_target_columns", target_columns)
        elif target_column:
            setattr(test_func, "_target_columns", [target_column])
        else:
            setattr(test_func, "_target_columns", None)
        setattr(test_func, "_description", description)
        setattr(test_func, "_severity", severity)
        return test_func

    if func is not None:
        return decorator(func)
    return decorator


class BaseTestPack:
    test_column_map: dict[str, str | list[str]] = {}

    def __init__(self, df: pd.DataFrame, trans_ref: str, enabled_tests: list[str] | None = None) -> None:
        self._df = df.copy()
        self.trans_ref = trans_ref
        self.enabled_tests = set(enabled_tests) if enabled_tests else None
        self._test_code_map = self._build_test_code_map()

    def _build_test_code_map(self) -> dict[str, str]:
        """
        Build deterministic test codes using format B{field_id}{n}.

        Example: Bpolicy_id1, Bpremium_amount1, Bclaim_amount1.
        """
        code_map: dict[str, str] = {}
        field_counters: dict[str, int] = {}

        for attribute_name in dir(self):
            if not attribute_name.startswith("test_"):
                continue

            method = getattr(self, attribute_name)
            if not callable(method) or not getattr(method, "_is_registered_test", False):
                continue

            target_columns = getattr(method, "_target_columns", None)
            if not target_columns:
                legacy_column = self.test_column_map.get(attribute_name)
                if legacy_column:
                    target_columns = [legacy_column] if isinstance(legacy_column, str) else legacy_column

            primary_field = "general"
            if target_columns and len(target_columns) > 0:
                primary_field = str(target_columns[0]).strip().lower() or "general"

            field_id = re.sub(r"[^a-z0-9_]+", "_", primary_field).strip("_") or "general"
            count = field_counters.get(field_id, 0) + 1
            field_counters[field_id] = count
            code_map[attribute_name] = f"B{field_id}{count}"

        return code_map

    def iter_registered_tests(self) -> list[Callable[[], pd.DataFrame | None]]:
        all_tests: list[Callable[[], pd.DataFrame | None]] = []
        filtered_tests: list[Callable[[], pd.DataFrame | None]] = []
        for attribute_name in dir(self):
            if not attribute_name.startswith("test_"):
                continue
            method = getattr(self, attribute_name)
            if callable(method) and getattr(method, "_is_registered_test", False):
                all_tests.append(method)
                test_code = self._test_code_map.get(attribute_name)
                short_name = attribute_name.replace("test_", "")
                if self.enabled_tests is None:
                    filtered_tests.append(method)
                    continue

                if (
                    attribute_name in self.enabled_tests
                    or short_name in self.enabled_tests
                    or test_code in self.enabled_tests
                ):
                    filtered_tests.append(method)

        if self.enabled_tests is not None and not filtered_tests:
            return all_tests
        return filtered_tests

    def run(self) -> list[PackFailure]:
        failures, _ = self.run_with_coverage()
        return failures

    def run_with_coverage(self) -> tuple[list[PackFailure], list[PackTestCoverage]]:
        failures: list[PackFailure] = []
        coverage: list[PackTestCoverage] = []
        for method in self.iter_registered_tests():
            result = method()
            test_name = method.__name__
            test_code = self._test_code_map.get(test_name)
            
            # Get target columns - support both new list format and legacy single column
            target_columns = getattr(method, "_target_columns", None)
            if not target_columns:
                legacy_column = self.test_column_map.get(test_name)
                if legacy_column:
                    target_columns = [legacy_column] if isinstance(legacy_column, str) else legacy_column
            
            if not target_columns:
                continue

            raw_description = getattr(method, "_description", None) or (method.__doc__ or "").strip()
            short_description = " ".join(raw_description.split()) if raw_description else test_name
            severity = getattr(method, "_severity", Severity.ERROR)

            if result is None or result.empty or self.trans_ref not in result.columns or "test_results" not in result.columns:
                coverage.append(
                    PackTestCoverage(
                        test_name=test_name,
                        test_code=test_code,
                        target_columns=target_columns,
                        description=short_description,
                        severity=severity,
                        evaluated_rows=0,
                        failed_rows=0,
                        passed_rows=0,
                    )
                )
                continue

            evaluated_rows = len(result)
            failing_rows = result.loc[~result["test_results"].fillna(False)]
            failed_rows = len(failing_rows)
            passed_rows = max(0, evaluated_rows - failed_rows)

            coverage.append(
                PackTestCoverage(
                    test_name=test_name,
                    test_code=test_code,
                    target_columns=target_columns,
                    description=short_description,
                    severity=severity,
                    evaluated_rows=evaluated_rows,
                    failed_rows=failed_rows,
                    passed_rows=passed_rows,
                )
            )

            if failing_rows.empty:
                continue

            failed_refs = {str(ref) for ref in failing_rows[self.trans_ref].dropna().astype(str).tolist()}
            if failed_refs:
                failures.append(
                    PackFailure(
                        test_name=test_name,
                        test_code=test_code,
                        target_columns=target_columns,
                        failed_refs=failed_refs,
                        description=short_description,
                        severity=severity,
                    )
                )

        return failures, coverage


def get_pack_class(name: str) -> type[BaseTestPack] | None:
    return TEST_PACKS.get(name.lower())
