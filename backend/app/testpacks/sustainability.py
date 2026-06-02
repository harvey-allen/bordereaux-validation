from __future__ import annotations

import pandas as pd

from app.testpacks.core import BaseTestPack, Severity, TestType, register_pack, register_test


class SustainabilityBaseTestPack(BaseTestPack):
    """Shared helpers for sustainability reporting packs."""

    def _select_columns(self, *columns: str) -> pd.DataFrame:
        requested_cols = list(dict.fromkeys([self.trans_ref] + list(columns)))
        existing_cols = [col for col in requested_cols if col in self._df.columns]
        data = self._df[existing_cols].copy()
        if self.trans_ref not in data.columns:
            data[self.trans_ref] = self._df.index.astype(str)
        return data

    def _present_series(self, column: str) -> pd.Series:
        if column not in self._df.columns:
            return pd.Series(False, index=self._df.index)
        values = self._df[column]
        return values.notna() & (values.astype(str).str.strip() != "")

    def _missing_rule(self, column: str) -> pd.DataFrame | None:
        if column not in self._df.columns:
            return None
        data = self._select_columns(column)
        data["test_results"] = self._present_series(column)
        return data[[self.trans_ref, "test_results"]]

    def _numeric_non_negative_rule(self, column: str) -> pd.DataFrame | None:
        if column not in self._df.columns:
            return None
        data = self._select_columns(column)
        values = pd.to_numeric(self._df[column], errors="coerce")
        data["test_results"] = values.notna() & (values >= 0)
        return data[[self.trans_ref, "test_results"]]


@register_pack("csrd")
class CsrdTestPack(SustainabilityBaseTestPack):
    """CSRD-focused mandatory and quality checks."""

    @register_test(target_column="Company Identifier", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CSRD0001_1(self) -> pd.DataFrame | None:
        """CSRD0001: Company Identifier must be present."""
        return self._missing_rule("Company Identifier")

    @register_test(target_column="Reporting Period Start", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CSRD0002_1(self) -> pd.DataFrame | None:
        """CSRD0002: Reporting Period Start must be present."""
        return self._missing_rule("Reporting Period Start")

    @register_test(target_column="Reporting Period End", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CSRD0003_1(self) -> pd.DataFrame | None:
        """CSRD0003: Reporting Period End must be present."""
        return self._missing_rule("Reporting Period End")

    @register_test(target_column="Scope 1 Emissions (tCO2e)", severity=Severity.ERROR, test_type=TestType.QUALITY)
    def test_CSRD0004_1(self) -> pd.DataFrame | None:
        """CSRD0004: Scope 1 Emissions must be numeric and non-negative."""
        return self._numeric_non_negative_rule("Scope 1 Emissions (tCO2e)")

    @register_test(target_column="Scope 2 Emissions (tCO2e)", severity=Severity.ERROR, test_type=TestType.QUALITY)
    def test_CSRD0005_1(self) -> pd.DataFrame | None:
        """CSRD0005: Scope 2 Emissions must be numeric and non-negative."""
        return self._numeric_non_negative_rule("Scope 2 Emissions (tCO2e)")

    @register_test(target_column="Scope 3 Emissions (tCO2e)", severity=Severity.ERROR, test_type=TestType.QUALITY)
    def test_CSRD0006_1(self) -> pd.DataFrame | None:
        """CSRD0006: Scope 3 Emissions must be numeric and non-negative."""
        return self._numeric_non_negative_rule("Scope 3 Emissions (tCO2e)")


@register_pack("tcfd")
class TcfdTestPack(SustainabilityBaseTestPack):
    """TCFD-focused mandatory and quality checks."""

    @register_test(target_column="Entity Name", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_TCFD0001_1(self) -> pd.DataFrame | None:
        """TCFD0001: Entity Name must be present."""
        return self._missing_rule("Entity Name")

    @register_test(target_column="Scenario Name", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_TCFD0002_1(self) -> pd.DataFrame | None:
        """TCFD0002: Scenario Name must be present."""
        return self._missing_rule("Scenario Name")

    @register_test(target_column="Metric Name", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_TCFD0003_1(self) -> pd.DataFrame | None:
        """TCFD0003: Metric Name must be present."""
        return self._missing_rule("Metric Name")

    @register_test(target_column="Metric Value", severity=Severity.ERROR, test_type=TestType.QUALITY)
    def test_TCFD0004_1(self) -> pd.DataFrame | None:
        """TCFD0004: Metric Value must be numeric and non-negative."""
        return self._numeric_non_negative_rule("Metric Value")

    @register_test(target_column="Climate Risk Category", severity=Severity.WARNING, test_type=TestType.QUALITY)
    def test_TCFD0005_1(self) -> pd.DataFrame | None:
        """TCFD0005: Climate Risk Category must be present."""
        return self._missing_rule("Climate Risk Category")

    @register_test(target_column="Horizon", severity=Severity.WARNING, test_type=TestType.QUALITY)
    def test_TCFD0006_1(self) -> pd.DataFrame | None:
        """TCFD0006: Horizon must be present."""
        return self._missing_rule("Horizon")
