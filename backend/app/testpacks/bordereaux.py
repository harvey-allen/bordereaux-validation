from __future__ import annotations

import pandas as pd

from app.testpacks.core import BaseTestPack, Severity, TestType, register_pack, register_test


class BordereauxBaseTestPack(BaseTestPack):
    """
    Shared base logic for all bordereaux-related packs.

    Specialized packs inherit these common tests and then add domain-specific
    tests for risk-and-premium and claims workflows.
    """

    def _select_columns(self, *columns: str) -> pd.DataFrame:
        requested_cols = list(dict.fromkeys([self.trans_ref] + list(columns)))
        existing_cols = [col for col in requested_cols if col in self._df.columns]
        data = self._df[existing_cols].copy()
        if self.trans_ref not in data.columns:
            data[self.trans_ref] = self._df.index.astype(str)
        return data

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

    def _missing_rule(self, column: str) -> pd.DataFrame | None:
        """Returns True (pass) for rows where the column is present and non-empty."""
        if column not in self._df.columns:
            return None
        data = self._select_columns(column)
        values = self._df[column]
        data["test_results"] = values.notna() & (values.astype(str).str.strip() != "")
        return data[[self.trans_ref, "test_results"]]

    def _present_series(self, column: str) -> pd.Series:
        if column not in self._df.columns:
            return pd.Series(False, index=self._df.index)
        values = self._df[column]
        return values.notna() & (values.astype(str).str.strip() != "")

    def _missing_with_fallback_rule(self, primary_column: str, fallback_column: str) -> pd.DataFrame | None:
        """Passes when primary is present, or fallback is present when primary is not."""
        if primary_column not in self._df.columns and fallback_column not in self._df.columns:
            return None
        data = self._select_columns(primary_column, fallback_column)
        primary_present = self._present_series(primary_column)
        fallback_present = self._present_series(fallback_column)
        data["test_results"] = primary_present | fallback_present
        return data[[self.trans_ref, "test_results"]]

    def _required_if_other_missing_rule(self, required_column: str, other_column: str) -> pd.DataFrame | None:
        """Passes when required column is present, unless the other column is present."""
        if required_column not in self._df.columns and other_column not in self._df.columns:
            return None
        data = self._select_columns(required_column, other_column)
        required_present = self._present_series(required_column)
        other_present = self._present_series(other_column)
        data["test_results"] = required_present | other_present
        return data[[self.trans_ref, "test_results"]]

    # ------------------------------------------------------------------
    # Mandatory fields common to both risk-and-premium and claims packs
    # ------------------------------------------------------------------

    @register_test(target_column="Reporting Period (End Date)", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0002_1(self) -> pd.DataFrame | None:
        """CR0002: Reporting Period (End Date) must be present."""
        return self._missing_rule("Reporting Period (End Date)")

    @register_test(target_column="Unique Market Reference (UMR)", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0005_1(self) -> pd.DataFrame | None:
        """CR0005: UMR must be present, unless Agreement No is present."""
        return self._missing_with_fallback_rule("Unique Market Reference (UMR)", "Agreement No")

    @register_test(target_column="Agreement No", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0006_1(self) -> pd.DataFrame | None:
        """CR0006: Agreement No must be present when UMR is missing."""
        return self._required_if_other_missing_rule("Agreement No", "Unique Market Reference (UMR)")

    @register_test(target_column="Coverholder Name", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0013_1(self) -> pd.DataFrame | None:
        """CR0013: Coverholder Name must be present."""
        return self._missing_rule("Coverholder Name")

    @register_test(target_column="Original Currency", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0020_1(self) -> pd.DataFrame | None:
        """CR0020: Original Currency must be present."""
        return self._missing_rule("Original Currency")


@register_pack("risk_and_premium")
class RiskAndPremiumBordereauxTestPack(BordereauxBaseTestPack):
    """Risk and premium bordereaux checks."""

    @register_test(target_column="Type of Insurance (Direct or Type or Reinsurance)", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0019_1(self) -> pd.DataFrame | None:
        """CR0019: Type of Insurance must be present."""
        return self._missing_rule("Type of Insurance (Direct or Type or Reinsurance)")

    @register_test(target_column="Total gross written premium", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0021_1(self) -> pd.DataFrame | None:
        """CR0021: Total gross written premium must be present."""
        return self._missing_rule("Total gross written premium")

    @register_test(target_column="Certificate Ref", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0029_1(self) -> pd.DataFrame | None:
        """CR0029: Certificate Ref must be present."""
        return self._missing_rule("Certificate Ref")

    @register_test(target_column="Risk Inception Date", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0030_1(self) -> pd.DataFrame | None:
        """CR0030: Risk Inception Date must be present."""
        return self._missing_rule("Risk Inception Date")

    @register_test(target_column="Risk Expiry Date", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0031_1(self) -> pd.DataFrame | None:
        """CR0031: Risk Expiry Date must be present."""
        return self._missing_rule("Risk Expiry Date")

    @register_test(target_column="Insured Full Name, Last Name or Company Name", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0035_1(self) -> pd.DataFrame | None:
        """CR0035: Insured Full Name, Last Name or Company Name must be present."""
        return self._missing_rule("Insured Full Name, Last Name or Company Name")

    @register_test(target_column="Insured Country (see code list)", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0041_1(self) -> pd.DataFrame | None:
        """CR0041: Insured Country must be present."""
        return self._missing_rule("Insured Country (see code list)")

    @register_test(target_column="Location of risk - Country", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0050_1(self) -> pd.DataFrame | None:
        """CR0050: Location of risk - Country must be present."""
        return self._missing_rule("Location of risk - Country")

    @register_test(target_column="Sum Insured Currency (see code list)", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0051_1(self) -> pd.DataFrame | None:
        """CR0051: Sum Insured Currency must be present."""
        return self._missing_rule("Sum Insured Currency (see code list)")

    @register_test(target_column="Sum Insured Amount", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0052_1(self) -> pd.DataFrame | None:
        """CR0052: Sum Insured Amount must be present."""
        return self._missing_rule("Sum Insured Amount")

    @register_test(target_column="Transaction Type - Original Premium etc.", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0056_1(self) -> pd.DataFrame | None:
        """CR0056: Transaction Type must be present."""
        return self._missing_rule("Transaction Type - Original Premium etc.")

    @register_test(target_column="Gross premium paid this time", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0059_1(self) -> pd.DataFrame | None:
        """CR0059: Gross premium paid this time must be present."""
        return self._missing_rule("Gross premium paid this time")

    @register_test(target_column="Commission %", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0061_1(self) -> pd.DataFrame | None:
        """CR0061: Commission % must be present."""
        return self._missing_rule("Commission %")

    @register_test(target_column="Commission Amount", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0062_1(self) -> pd.DataFrame | None:
        """CR0062: Commission Amount must be present."""
        return self._missing_rule("Commission Amount")

    @register_test(target_column="Net Premium to London in original currency", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0065_1(self) -> pd.DataFrame | None:
        """CR0065: Net Premium to London in original currency must be present."""
        return self._missing_rule("Net Premium to London in original currency")

    @register_test(target_column="Settlement Currency", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0066_1(self) -> pd.DataFrame | None:
        """CR0066: Settlement Currency must be present."""
        return self._missing_rule("Settlement Currency")


@register_pack("claims")
class ClaimsBordereauxTestPack(BordereauxBaseTestPack):
    """Claims bordereaux checks."""

    @register_test(target_column="Binding authority or coverholder appointment agreement inception date", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0008_1(self) -> pd.DataFrame | None:
        """CR0008: Binding authority inception date must be present."""
        return self._missing_rule("Binding authority or coverholder appointment agreement inception date")

    @register_test(target_column="Binding authority or coverholder appointment agreement expiry date", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0009_1(self) -> pd.DataFrame | None:
        """CR0009: Binding authority expiry date must be present."""
        return self._missing_rule("Binding authority or coverholder appointment agreement expiry date")

    @register_test(target_column="Certificate Reference", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0029_1(self) -> pd.DataFrame | None:
        """CR0029: Certificate Reference must be present."""
        return self._missing_rule("Certificate Reference")

    @register_test(target_column="Insured Full Name or Company Name", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0035_1(self) -> pd.DataFrame | None:
        """CR0035: Insured Full Name or Company Name must be present."""
        return self._missing_rule("Insured Full Name or Company Name")

    @register_test(target_column="Insured Country", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0041_1(self) -> pd.DataFrame | None:
        """CR0041: Insured Country must be present."""
        return self._missing_rule("Insured Country")

    @register_test(target_column="Claim Reference / Number", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0104_1(self) -> pd.DataFrame | None:
        """CR0104: Claim Reference / Number must be present."""
        return self._missing_rule("Claim Reference / Number")

    @register_test(target_column="Claim Status", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0105_1(self) -> pd.DataFrame | None:
        """CR0105: Claim Status must be present."""
        return self._missing_rule("Claim Status")

    @register_test(target_column="Refer to Underwriters", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0106_1(self) -> pd.DataFrame | None:
        """CR0106: Refer to Underwriters must be present."""
        return self._missing_rule("Refer to Underwriters")

    @register_test(target_column="Denial", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0107_1(self) -> pd.DataFrame | None:
        """CR0107: Denial must be present."""
        return self._missing_rule("Denial")

    @register_test(target_column="Original Currency", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0109_1(self) -> pd.DataFrame | None:
        """CR0109: Original Currency must be present."""
        return self._missing_rule("Original Currency")

    @register_test(target_column="Location of loss Country", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0116_1(self) -> pd.DataFrame | None:
        """CR0116: Location of loss Country must be present."""
        return self._missing_rule("Location of loss Country")

    @register_test(target_column="Paid this month - Indemnity", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0126_1(self) -> pd.DataFrame | None:
        """CR0126: Paid this month - Indemnity must be present."""
        return self._missing_rule("Paid this month - Indemnity")

    @register_test(target_column="Paid this month - Fees", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0127_1(self) -> pd.DataFrame | None:
        """CR0127: Paid this month - Fees must be present."""
        return self._missing_rule("Paid this month - Fees")

    @register_test(target_column="Previously Paid - Indemnity", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0128_1(self) -> pd.DataFrame | None:
        """CR0128: Previously Paid - Indemnity must be present."""
        return self._missing_rule("Previously Paid - Indemnity")

    @register_test(target_column="Previously Paid - Fees", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0129_1(self) -> pd.DataFrame | None:
        """CR0129: Previously Paid - Fees must be present."""
        return self._missing_rule("Previously Paid - Fees")

    @register_test(target_column="Reserve - Indemnity", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0130_1(self) -> pd.DataFrame | None:
        """CR0130: Reserve - Indemnity must be present."""
        return self._missing_rule("Reserve - Indemnity")

    @register_test(target_column="Reserve - Fees", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0131_1(self) -> pd.DataFrame | None:
        """CR0131: Reserve - Fees must be present."""
        return self._missing_rule("Reserve - Fees")

    @register_test(target_column="Total Incurred - Indemnity", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0134_1(self) -> pd.DataFrame | None:
        """CR0134: Total Incurred - Indemnity must be present."""
        return self._missing_rule("Total Incurred - Indemnity")

    @register_test(target_column="Total Incurred - Fees", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0135_1(self) -> pd.DataFrame | None:
        """CR0135: Total Incurred - Fees must be present."""
        return self._missing_rule("Total Incurred - Fees")

    @register_test(target_column="Date Claim First Advised/Date Claim Made", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0136_1(self) -> pd.DataFrame | None:
        """CR0136: Date Claim First Advised/Date Claim Made must be present."""
        return self._missing_rule("Date Claim First Advised/Date Claim Made")

    @register_test(target_column="Date Claim Opened", severity=Severity.CRITICAL, test_type=TestType.MISSING)
    def test_CR0300_1(self) -> pd.DataFrame | None:
        """CR0300: Date Claim Opened must be present."""
        return self._missing_rule("Date Claim Opened")
