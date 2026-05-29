from __future__ import annotations

import pandas as pd

from app.testpacks.core import BaseTestPack, Severity, register_pack, register_test


class BordereauxBaseTestPack(BaseTestPack):
    """
    Shared base logic for all bordereaux-related packs.

    Specialized packs inherit these common tests and then add domain-specific
    tests for premium and claims workflows.
    """

    def _select_columns(self, *columns: str) -> pd.DataFrame:
        cols = list(dict.fromkeys([self.trans_ref] + list(columns)))
        return self._df[cols].copy()

    def _string_rule(self, column: str, predicate) -> pd.DataFrame | None:
        if column not in self._df.columns:
            return None
        data = self._select_columns(column)
        values = self._df[column].astype(str).str.strip()
        data["test_results"] = predicate(values)
        return data[[self.trans_ref, "test_results"]]

    def _numeric_rule(self, column: str, predicate) -> pd.DataFrame | None:
        if column not in self._df.columns:
            return None
        data = self._select_columns(column)
        values = pd.to_numeric(self._df[column], errors="coerce")
        data["test_results"] = predicate(values)
        return data[[self.trans_ref, "test_results"]]

    @register_test(target_column="Unique Market Reference (UMR)", severity=Severity.CRITICAL)
    def test_CR0005_1(self) -> pd.DataFrame | None:
        """Example failing test: UMR must start with UKX-."""
        return self._string_rule("Unique Market Reference (UMR)", lambda s: s.str.startswith("UKX-"))

    @register_test(target_column="Reporting Period (End Date)", severity=Severity.ERROR)
    def test_CR0002_1(self) -> pd.DataFrame | None:
        """Example failing test: reporting period end must be 2030 or later."""
        return self._string_rule("Reporting Period (End Date)", lambda s: s.str[:4].astype(str) >= "2030")

    @register_test(target_column="Coverholder Name", severity=Severity.WARNING)
    def test_CR0013_1(self) -> pd.DataFrame | None:
        """Example failing test: coverholder name must include 'Lloyd'."""
        return self._string_rule("Coverholder Name", lambda s: s.str.contains("Lloyd", case=False, na=False))

    @register_test(target_column="Original Currency", severity=Severity.ERROR)
    def test_CR0020_1(self) -> pd.DataFrame | None:
        """Example failing test: original currency must be USD."""
        return self._string_rule("Original Currency", lambda s: s.eq("USD"))

    @register_test(target_column="Gross premium paid this time", severity=Severity.ERROR)
    def test_CR0059_1(self) -> pd.DataFrame | None:
        """Example failing test: gross premium must exceed 1,000,000."""
        return self._numeric_rule("Gross premium paid this time", lambda n: n > 1_000_000)

    @register_test(target_column="Claim Reference / Number", severity=Severity.CRITICAL)
    def test_CR0104_1(self) -> pd.DataFrame | None:
        """Example failing test: claim reference must start with UK-CLM-."""
        return self._string_rule("Claim Reference / Number", lambda s: s.str.startswith("UK-CLM-"))

    @register_test(target_column="Date Claim First Advised/Date Claim Made", severity=Severity.ERROR)
    def test_CR0136_1(self) -> pd.DataFrame | None:
        """Example failing test: advised date must be before 2020-01-01."""
        return self._string_rule("Date Claim First Advised/Date Claim Made", lambda s: s < "2020-01-01")

    @register_test(target_column="Claim Status", severity=Severity.WARNING)
    def test_CR0105_1(self) -> pd.DataFrame | None:
        """Example failing test: claim status must be REOPENED."""
        return self._string_rule("Claim Status", lambda s: s.eq("REOPENED"))

    @register_test(target_column="Paid this month - Indemnity", severity=Severity.ERROR)
    def test_CR0126_1(self) -> pd.DataFrame | None:
        """Example failing test: paid indemnity this month must be exactly zero."""
        return self._numeric_rule("Paid this month - Indemnity", lambda n: n == 0)

    @register_test(target_column="Insured Country", severity=Severity.WARNING)
    def test_CR0041_1(self) -> pd.DataFrame | None:
        """Example failing test: insured country must be DE."""
        return self._string_rule("Insured Country", lambda s: s.eq("DE"))


@register_pack("premium")
class PremiumBordereauxTestPack(BordereauxBaseTestPack):
    """Premium bordereaux checks."""


@register_pack("claims")
class ClaimsBordereauxTestPack(BordereauxBaseTestPack):
    """Claims bordereaux checks."""
