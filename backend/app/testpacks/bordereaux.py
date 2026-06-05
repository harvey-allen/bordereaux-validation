from __future__ import annotations

import pandas as pd

from app.testpacks.core import BaseTestPack, Severity, TestType, register_pack, register_test

# Tolerance (absolute) used for floating-point arithmetic cross-checks
_ARITHMETIC_TOLERANCE = 0.01


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

    def _date_rule(self, column: str) -> pd.DataFrame | None:
        """Pass if the value is blank or can be parsed as a date."""
        if column not in self._df.columns:
            return None
        data = self._select_columns(column)
        present = self._present_series(column)
        parsed = pd.to_datetime(self._df[column], errors="coerce", dayfirst=True)
        data["test_results"] = ~present | parsed.notna()
        return data[[self.trans_ref, "test_results"]]

    def _currency_code_rule(self, column: str) -> pd.DataFrame | None:
        """Pass if the value is blank or is a valid ISO 4217 three-letter currency code (e.g. GBP)."""
        if column not in self._df.columns:
            return None
        data = self._select_columns(column)
        present = self._present_series(column)
        values = self._df[column].astype(str).str.strip()
        data["test_results"] = ~present | values.str.fullmatch(r"[A-Z]{3}").fillna(False)
        return data[[self.trans_ref, "test_results"]]

    def _country_code_rule(self, column: str) -> pd.DataFrame | None:
        """Pass if the value is blank or matches ISO 3166-1 alpha-2 or alpha-3 (e.g. GB or GBR)."""
        if column not in self._df.columns:
            return None
        data = self._select_columns(column)
        present = self._present_series(column)
        values = self._df[column].astype(str).str.strip()
        data["test_results"] = ~present | values.str.fullmatch(r"[A-Z]{2,3}").fillna(False)
        return data[[self.trans_ref, "test_results"]]

    def _date_order_rule(self, earlier_col: str, later_col: str) -> pd.DataFrame | None:
        """Pass if either column is blank/unparseable, or earlier date <= later date."""
        if earlier_col not in self._df.columns and later_col not in self._df.columns:
            return None
        data = self._select_columns(
            *[c for c in (earlier_col, later_col) if c in self._df.columns]
        )
        earlier_raw = (
            self._df[earlier_col]
            if earlier_col in self._df.columns
            else pd.Series(pd.NaT, index=self._df.index)
        )
        later_raw = (
            self._df[later_col]
            if later_col in self._df.columns
            else pd.Series(pd.NaT, index=self._df.index)
        )
        earlier = pd.to_datetime(earlier_raw, errors="coerce", dayfirst=True)
        later = pd.to_datetime(later_raw, errors="coerce", dayfirst=True)
        both_present = earlier.notna() & later.notna()
        data["test_results"] = ~both_present | (earlier <= later)
        return data[[self.trans_ref, "test_results"]]

    def _not_future_rule(self, column: str) -> pd.DataFrame | None:
        """Pass if the value is blank, unparseable, or not in the future."""
        if column not in self._df.columns:
            return None
        data = self._select_columns(column)
        parsed = pd.to_datetime(self._df[column], errors="coerce", dayfirst=True)
        today = pd.Timestamp.now().normalize()
        data["test_results"] = parsed.isna() | (parsed <= today)
        return data[[self.trans_ref, "test_results"]]

    def _numeric_present_rule(self, column: str) -> pd.DataFrame | None:
        """Pass if the value is blank or can be parsed as a number."""
        if column not in self._df.columns:
            return None
        data = self._select_columns(column)
        present = self._present_series(column)
        numeric = pd.to_numeric(self._df[column], errors="coerce")
        data["test_results"] = ~present | numeric.notna()
        return data[[self.trans_ref, "test_results"]]

    def _arithmetic_check_rule(
        self,
        result_col: str,
        *addend_cols: str,
        tolerance: float = _ARITHMETIC_TOLERANCE,
    ) -> pd.DataFrame | None:
        """Pass if any column is blank/non-numeric, or result equals sum(addends) within tolerance."""
        all_cols = [result_col] + list(addend_cols)
        if not any(c in self._df.columns for c in all_cols):
            return None
        present_cols = [c for c in all_cols if c in self._df.columns]
        data = self._select_columns(*present_cols)

        def _to_numeric(col: str) -> pd.Series:
            if col in self._df.columns:
                return pd.to_numeric(self._df[col], errors="coerce")
            return pd.Series(pd.NA, index=self._df.index, dtype="float64")

        result = _to_numeric(result_col)
        addends = [_to_numeric(c) for c in addend_cols]

        total = addends[0].copy()
        for s in addends[1:]:
            total = total + s

        present_mask = result.notna()
        for s in addends:
            present_mask = present_mask & s.notna()

        data["test_results"] = ~present_mask | ((result - total).abs() <= tolerance)
        return data[[self.trans_ref, "test_results"]]

    def _binary_formula_rule(
        self,
        result_col: str,
        first_operand_col: str,
        second_operand_col: str,
        formula,
        *,
        tolerance: float = _ARITHMETIC_TOLERANCE,
    ) -> pd.DataFrame | None:
        """Pass if values are blank/non-numeric, or result matches formula within tolerance."""
        required_cols = (result_col, first_operand_col, second_operand_col)
        if not all(col in self._df.columns for col in required_cols):
            return None

        data = self._select_columns(*required_cols)
        result = pd.to_numeric(self._df[result_col], errors="coerce")
        first = pd.to_numeric(self._df[first_operand_col], errors="coerce")
        second = pd.to_numeric(self._df[second_operand_col], errors="coerce")
        expected = formula(first, second)
        present_mask = result.notna() & first.notna() & second.notna()
        data["test_results"] = ~present_mask | ((result - expected).abs() <= tolerance)
        return data[[self.trans_ref, "test_results"]]

    def _date_not_older_than_months_rule(
        self,
        earlier_col: str,
        reference_col: str,
        *,
        months: int,
    ) -> pd.DataFrame | None:
        """Pass if values are blank/unparseable, or earlier date is within N months of reference."""
        if earlier_col not in self._df.columns and reference_col not in self._df.columns:
            return None

        present_cols = [c for c in (earlier_col, reference_col) if c in self._df.columns]
        data = self._select_columns(*present_cols)

        earlier = pd.to_datetime(
            self._df[earlier_col] if earlier_col in self._df.columns else pd.Series(pd.NaT, index=self._df.index),
            errors="coerce",
            dayfirst=True,
        )
        reference = pd.to_datetime(
            self._df[reference_col] if reference_col in self._df.columns else pd.Series(pd.NaT, index=self._df.index),
            errors="coerce",
            dayfirst=True,
        )
        both_present = earlier.notna() & reference.notna()
        cutoff = reference - pd.DateOffset(months=months)
        data["test_results"] = ~both_present | (earlier >= cutoff)
        return data[[self.trans_ref, "test_results"]]

    # ------------------------------------------------------------------
    # Mandatory fields common to both risk-and-premium and claims packs
    # ------------------------------------------------------------------

    @register_test(target_column="Reporting Period (End Date)", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0002_1(self) -> pd.DataFrame | None:
        """CR0002: Reporting Period (End Date) must be present."""
        return self._missing_rule("Reporting Period (End Date)")

    @register_test(target_column="Reporting Period (End Date)", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0002_2(self) -> pd.DataFrame | None:
        """CR0002: Reporting Period (End Date) must be a valid date."""
        return self._date_rule("Reporting Period (End Date)")

    @register_test(target_column="Reporting Period (End Date)", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0002_3(self) -> pd.DataFrame | None:
        """CR0002: Reporting Period End Date must be on or after Reporting Period Start Date."""
        return self._date_order_rule("Reporting Period Start Date", "Reporting Period (End Date)")

    @register_test(target_column="Reporting Period (End Date)", severity=Severity.WARNING, test_type=TestType.LOGIC)
    def test_CR0002_4(self) -> pd.DataFrame | None:
        """CR0002: Reporting Period End Date must not be in the future."""
        return self._not_future_rule("Reporting Period (End Date)")

    @register_test(target_column="Reporting Period Start Date", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0001_2(self) -> pd.DataFrame | None:
        """CR0001: Reporting Period Start Date must be a valid date."""
        return self._date_rule("Reporting Period Start Date")

    @register_test(target_column="Unique Market Reference (UMR)", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0005_1(self) -> pd.DataFrame | None:
        """CR0005: UMR must be present, unless Agreement No is present."""
        return self._missing_with_fallback_rule("Unique Market Reference (UMR)", "Agreement No")

    @register_test(target_column="Agreement No", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0006_1(self) -> pd.DataFrame | None:
        """CR0006: Agreement No must be present when UMR is missing."""
        return self._required_if_other_missing_rule("Agreement No", "Unique Market Reference (UMR)")

    @register_test(target_column="Coverholder Name", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0013_1(self) -> pd.DataFrame | None:
        """CR0013: Coverholder Name must be present."""
        return self._missing_rule("Coverholder Name")

    @register_test(target_column="Original Currency", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0020_1(self) -> pd.DataFrame | None:
        """CR0020: Original Currency must be present."""
        return self._missing_rule("Original Currency")

    @register_test(target_column="Original Currency", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0020_2(self) -> pd.DataFrame | None:
        """CR0020: Original Currency must be a valid ISO 4217 three-letter currency code."""
        return self._currency_code_rule("Original Currency")

    @register_test(target_column="Risk Inception Date", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0030_2(self) -> pd.DataFrame | None:
        """CR0030: Risk Inception Date must be a valid date."""
        return self._date_rule("Risk Inception Date")

    @register_test(target_column="Risk Inception Date", severity=Severity.WARNING, test_type=TestType.LOGIC)
    def test_CR0030_3(self) -> pd.DataFrame | None:
        """CR0030: Risk Inception Date must not be in the future."""
        return self._not_future_rule("Risk Inception Date")

    @register_test(target_column="Risk Expiry Date", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0031_2(self) -> pd.DataFrame | None:
        """CR0031: Risk Expiry Date must be a valid date."""
        return self._date_rule("Risk Expiry Date")

    @register_test(target_column="Risk Expiry Date", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0031_3(self) -> pd.DataFrame | None:
        """CR0031: Risk Expiry Date must be on or after Risk Inception Date."""
        return self._date_order_rule("Risk Inception Date", "Risk Expiry Date")

    @register_test(target_column="Rate of Exchange", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0067_2(self) -> pd.DataFrame | None:
        """Rate of Exchange must be numeric."""
        return self._numeric_present_rule("Rate of Exchange")

    @register_test(target_column="Rate of Exchange", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0067_3(self) -> pd.DataFrame | None:
        """Rate of Exchange must be greater than zero."""
        return self._numeric_rule("Rate of Exchange", lambda v: v.isna() | (v > 0))


@register_pack("risk_and_premium")
class RiskAndPremiumBordereauxTestPack(BordereauxBaseTestPack):
    """Risk and premium bordereaux checks."""

    @register_test(target_column="Type of Insurance (Direct or Type or Reinsurance)", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0019_1(self) -> pd.DataFrame | None:
        """CR0019: Type of Insurance must be present."""
        return self._missing_rule("Type of Insurance (Direct or Type or Reinsurance)")

    @register_test(target_column="Total gross written premium", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0021_1(self) -> pd.DataFrame | None:
        """CR0021: Total gross written premium must be present."""
        return self._missing_rule("Total gross written premium")

    @register_test(target_column="Certificate Ref", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0029_1(self) -> pd.DataFrame | None:
        """CR0029: Certificate Ref must be present."""
        return self._missing_rule("Certificate Ref")

    @register_test(target_column="Risk Inception Date", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0030_1(self) -> pd.DataFrame | None:
        """CR0030: Risk Inception Date must be present."""
        return self._missing_rule("Risk Inception Date")

    @register_test(target_column="Risk Expiry Date", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0031_1(self) -> pd.DataFrame | None:
        """CR0031: Risk Expiry Date must be present."""
        return self._missing_rule("Risk Expiry Date")

    @register_test(target_column="Insured Full Name, Last Name or Company Name", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0035_1(self) -> pd.DataFrame | None:
        """CR0035: Insured Full Name, Last Name or Company Name must be present."""
        return self._missing_rule("Insured Full Name, Last Name or Company Name")

    @register_test(target_column="Insured Country (see code list)", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0041_1(self) -> pd.DataFrame | None:
        """CR0041: Insured Country must be present."""
        return self._missing_rule("Insured Country (see code list)")

    @register_test(target_column="Location of risk - Country", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0050_1(self) -> pd.DataFrame | None:
        """CR0050: Location of risk - Country must be present."""
        return self._missing_rule("Location of risk - Country")

    @register_test(target_column="Sum Insured Currency (see code list)", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0051_1(self) -> pd.DataFrame | None:
        """CR0051: Sum Insured Currency must be present."""
        return self._missing_rule("Sum Insured Currency (see code list)")

    @register_test(target_column="Sum Insured Amount", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0052_1(self) -> pd.DataFrame | None:
        """CR0052: Sum Insured Amount must be present."""
        return self._missing_rule("Sum Insured Amount")

    @register_test(target_column="Transaction Type - Original Premium etc.", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0056_1(self) -> pd.DataFrame | None:
        """CR0056: Transaction Type must be present."""
        return self._missing_rule("Transaction Type - Original Premium etc.")

    @register_test(target_column="Gross premium paid this time", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0059_1(self) -> pd.DataFrame | None:
        """CR0059: Gross premium paid this time must be present."""
        return self._missing_rule("Gross premium paid this time")

    @register_test(target_column="Commission %", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0061_1(self) -> pd.DataFrame | None:
        """CR0061: Commission % must be present."""
        return self._missing_rule("Commission %")

    @register_test(target_column="Commission Amount", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0062_1(self) -> pd.DataFrame | None:
        """CR0062: Commission Amount must be present."""
        return self._missing_rule("Commission Amount")

    @register_test(target_column="Net Premium to London in original currency", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0065_1(self) -> pd.DataFrame | None:
        """CR0065: Net Premium to London in original currency must be present."""
        return self._missing_rule("Net Premium to London in original currency")

    @register_test(target_column="Settlement Currency", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0066_1(self) -> pd.DataFrame | None:
        """CR0066: Settlement Currency must be present."""
        return self._missing_rule("Settlement Currency")

    # ------------------------------------------------------------------
    # DATA TYPE checks
    # ------------------------------------------------------------------

    @register_test(target_column="Total gross written premium", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0021_2(self) -> pd.DataFrame | None:
        """CR0021: Total gross written premium must be numeric."""
        return self._numeric_present_rule("Total gross written premium")

    @register_test(target_column="Sum Insured Amount", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0052_2(self) -> pd.DataFrame | None:
        """CR0052: Sum Insured Amount must be numeric."""
        return self._numeric_present_rule("Sum Insured Amount")

    @register_test(target_column="Gross premium paid this time", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0059_2(self) -> pd.DataFrame | None:
        """CR0059: Gross premium paid this time must be numeric."""
        return self._numeric_present_rule("Gross premium paid this time")

    @register_test(target_column="Commission %", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0061_2(self) -> pd.DataFrame | None:
        """CR0061: Commission % must be numeric."""
        return self._numeric_present_rule("Commission %")

    @register_test(target_column="Commission Amount", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0062_2(self) -> pd.DataFrame | None:
        """CR0062: Commission Amount must be numeric."""
        return self._numeric_present_rule("Commission Amount")

    @register_test(target_column="Net Premium to London in original currency", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0065_2(self) -> pd.DataFrame | None:
        """CR0065: Net Premium to London in original currency must be numeric."""
        return self._numeric_present_rule("Net Premium to London in original currency")

    @register_test(target_column="Settlement Currency", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0066_2(self) -> pd.DataFrame | None:
        """CR0066: Settlement Currency must be a valid ISO 4217 three-letter currency code."""
        return self._currency_code_rule("Settlement Currency")

    @register_test(target_column="Net Premium to London in Settlement Currency", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0068_2(self) -> pd.DataFrame | None:
        """CR0068: Net Premium to London in Settlement Currency must be numeric."""
        return self._numeric_present_rule("Net Premium to London in Settlement Currency")

    @register_test(target_column="Sum Insured Currency (see code list)", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0051_2(self) -> pd.DataFrame | None:
        """CR0051: Sum Insured Currency must be a valid ISO 4217 three-letter currency code."""
        return self._currency_code_rule("Sum Insured Currency (see code list)")

    @register_test(target_column="Insured Country (see code list)", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0041_2(self) -> pd.DataFrame | None:
        """CR0041: Insured Country must be a valid ISO 3166-1 alpha-2 or alpha-3 country code."""
        return self._country_code_rule("Insured Country (see code list)")

    @register_test(target_column="Location of risk - Country", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0050_2(self) -> pd.DataFrame | None:
        """CR0050: Location of risk - Country must be a valid ISO 3166-1 alpha-2 or alpha-3 country code."""
        return self._country_code_rule("Location of risk - Country")

    @register_test(target_column="Effective Date of Transaction", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0057_2(self) -> pd.DataFrame | None:
        """CR0057: Effective Date of Transaction must be a valid date."""
        return self._date_rule("Effective Date of Transaction")

    @register_test(target_column="Expiry Date of Transaction", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0058_2(self) -> pd.DataFrame | None:
        """CR0058: Expiry Date of Transaction must be a valid date."""
        return self._date_rule("Expiry Date of Transaction")

    # ------------------------------------------------------------------
    # LOGIC checks
    # ------------------------------------------------------------------

    @register_test(target_column="Effective Date of Transaction", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0057_3(self) -> pd.DataFrame | None:
        """CR0057: Effective Date of Transaction must not be before Risk Inception Date."""
        return self._date_order_rule("Risk Inception Date", "Effective Date of Transaction")

    @register_test(target_column="Expiry Date of Transaction", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0058_3(self) -> pd.DataFrame | None:
        """CR0058: Expiry Date of Transaction must not be after Risk Expiry Date."""
        return self._date_order_rule("Expiry Date of Transaction", "Risk Expiry Date")

    @register_test(target_column="Commission %", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0061_3(self) -> pd.DataFrame | None:
        """CR0061: Commission % must be between 0 and 100."""
        return self._numeric_rule(
            "Commission %",
            lambda v: v.isna() | ((v >= 0) & (v <= 100)),
        )

    @register_test(target_column="Commission Amount", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0062_3(self) -> pd.DataFrame | None:
        """CR0062: Commission Amount must equal Commission % / 100 × Gross premium paid this time."""
        return self._binary_formula_rule(
            "Commission Amount",
            "Commission %",
            "Gross premium paid this time",
            lambda pct, gross: (pct / 100) * gross,
        )

    @register_test(target_column="Net Premium to London in original currency", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0065_3(self) -> pd.DataFrame | None:
        """CR0065: Net Premium to London in original currency must equal Gross premium paid this time minus Commission Amount."""
        return self._binary_formula_rule(
            "Net Premium to London in original currency",
            "Gross premium paid this time",
            "Commission Amount",
            lambda gross, commission: gross - commission,
        )

    @register_test(target_column="% for Lloyd's", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0076_3(self) -> pd.DataFrame | None:
        """CR0076: % for Lloyd's must be between 0 and 100."""
        return self._numeric_rule(
            "% for Lloyd's",
            lambda v: v.isna() | ((v >= 0) & (v <= 100)),
        )


@register_pack("claims")
class ClaimsBordereauxTestPack(BordereauxBaseTestPack):
    """Claims bordereaux checks."""

    @register_test(target_column="Binding authority or coverholder appointment agreement inception date", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0008_1(self) -> pd.DataFrame | None:
        """CR0008: Binding authority inception date must be present."""
        return self._missing_rule("Binding authority or coverholder appointment agreement inception date")

    @register_test(target_column="Binding authority or coverholder appointment agreement expiry date", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0009_1(self) -> pd.DataFrame | None:
        """CR0009: Binding authority expiry date must be present."""
        return self._missing_rule("Binding authority or coverholder appointment agreement expiry date")

    @register_test(target_column="Certificate Reference", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0029_1(self) -> pd.DataFrame | None:
        """CR0029: Certificate Reference must be present."""
        return self._missing_rule("Certificate Reference")

    @register_test(target_column="Insured Full Name or Company Name", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0035_1(self) -> pd.DataFrame | None:
        """CR0035: Insured Full Name or Company Name must be present."""
        return self._missing_rule("Insured Full Name or Company Name")

    @register_test(target_column="Insured Country", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0041_1(self) -> pd.DataFrame | None:
        """CR0041: Insured Country must be present."""
        return self._missing_rule("Insured Country")

    @register_test(target_column="Claim Reference / Number", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0104_1(self) -> pd.DataFrame | None:
        """CR0104: Claim Reference / Number must be present."""
        return self._missing_rule("Claim Reference / Number")

    @register_test(target_column="Claim Status", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0105_1(self) -> pd.DataFrame | None:
        """CR0105: Claim Status must be present."""
        return self._missing_rule("Claim Status")

    @register_test(target_column="Refer to Underwriters", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0106_1(self) -> pd.DataFrame | None:
        """CR0106: Refer to Underwriters must be present."""
        return self._missing_rule("Refer to Underwriters")

    @register_test(target_column="Denial", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0107_1(self) -> pd.DataFrame | None:
        """CR0107: Denial must be present."""
        return self._missing_rule("Denial")

    @register_test(target_column="Original Currency", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0109_1(self) -> pd.DataFrame | None:
        """CR0109: Original Currency must be present."""
        return self._missing_rule("Original Currency")

    @register_test(target_column="Location of loss Country", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0116_1(self) -> pd.DataFrame | None:
        """CR0116: Location of loss Country must be present."""
        return self._missing_rule("Location of loss Country")

    @register_test(target_column="Paid this month - Indemnity", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0126_1(self) -> pd.DataFrame | None:
        """CR0126: Paid this month - Indemnity must be present."""
        return self._missing_rule("Paid this month - Indemnity")

    @register_test(target_column="Paid this month - Fees", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0127_1(self) -> pd.DataFrame | None:
        """CR0127: Paid this month - Fees must be present."""
        return self._missing_rule("Paid this month - Fees")

    @register_test(target_column="Previously Paid - Indemnity", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0128_1(self) -> pd.DataFrame | None:
        """CR0128: Previously Paid - Indemnity must be present."""
        return self._missing_rule("Previously Paid - Indemnity")

    @register_test(target_column="Previously Paid - Fees", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0129_1(self) -> pd.DataFrame | None:
        """CR0129: Previously Paid - Fees must be present."""
        return self._missing_rule("Previously Paid - Fees")

    @register_test(target_column="Reserve - Indemnity", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0130_1(self) -> pd.DataFrame | None:
        """CR0130: Reserve - Indemnity must be present."""
        return self._missing_rule("Reserve - Indemnity")

    @register_test(target_column="Reserve - Fees", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0131_1(self) -> pd.DataFrame | None:
        """CR0131: Reserve - Fees must be present."""
        return self._missing_rule("Reserve - Fees")

    @register_test(target_column="Total Incurred - Indemnity", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0134_1(self) -> pd.DataFrame | None:
        """CR0134: Total Incurred - Indemnity must be present."""
        return self._missing_rule("Total Incurred - Indemnity")

    @register_test(target_column="Total Incurred - Fees", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0135_1(self) -> pd.DataFrame | None:
        """CR0135: Total Incurred - Fees must be present."""
        return self._missing_rule("Total Incurred - Fees")

    @register_test(target_column="Date Claim First Advised/Date Claim Made", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0136_1(self) -> pd.DataFrame | None:
        """CR0136: Date Claim First Advised/Date Claim Made must be present."""
        return self._missing_rule("Date Claim First Advised/Date Claim Made")

    @register_test(target_column="Date Claim Opened", severity=Severity.CRITICAL, test_type=TestType.COMPLETENESS)
    def test_CR0300_1(self) -> pd.DataFrame | None:
        """CR0300: Date Claim Opened must be present."""
        return self._missing_rule("Date Claim Opened")

    # ------------------------------------------------------------------
    # DATA TYPE checks
    # ------------------------------------------------------------------

    @register_test(target_column="Binding authority or coverholder appointment agreement inception date", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0008_2(self) -> pd.DataFrame | None:
        """CR0008: Binding authority inception date must be a valid date."""
        return self._date_rule("Binding authority or coverholder appointment agreement inception date")

    @register_test(target_column="Binding authority or coverholder appointment agreement expiry date", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0009_2(self) -> pd.DataFrame | None:
        """CR0009: Binding authority expiry date must be a valid date."""
        return self._date_rule("Binding authority or coverholder appointment agreement expiry date")

    @register_test(target_column="Original Currency", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0109_2(self) -> pd.DataFrame | None:
        """CR0109: Original Currency must be a valid ISO 4217 three-letter currency code."""
        return self._currency_code_rule("Original Currency")

    @register_test(target_column="Settlement Currency", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0110_2(self) -> pd.DataFrame | None:
        """CR0110: Settlement Currency must be a valid ISO 4217 three-letter currency code."""
        return self._currency_code_rule("Settlement Currency")

    @register_test(target_column="Insured Country", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0041_2(self) -> pd.DataFrame | None:
        """CR0041: Insured Country must be a valid ISO 3166-1 alpha-2 or alpha-3 country code."""
        return self._country_code_rule("Insured Country")

    @register_test(target_column="Location of loss Country", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0116_2(self) -> pd.DataFrame | None:
        """CR0116: Location of loss Country must be a valid ISO 3166-1 alpha-2 or alpha-3 country code."""
        return self._country_code_rule("Location of loss Country")

    @register_test(target_column="Paid this month - Indemnity", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0126_2(self) -> pd.DataFrame | None:
        """CR0126: Paid this month - Indemnity must be numeric."""
        return self._numeric_present_rule("Paid this month - Indemnity")

    @register_test(target_column="Paid this month - Fees", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0127_2(self) -> pd.DataFrame | None:
        """CR0127: Paid this month - Fees must be numeric."""
        return self._numeric_present_rule("Paid this month - Fees")

    @register_test(target_column="Previously Paid - Indemnity", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0128_2(self) -> pd.DataFrame | None:
        """CR0128: Previously Paid - Indemnity must be numeric."""
        return self._numeric_present_rule("Previously Paid - Indemnity")

    @register_test(target_column="Previously Paid - Fees", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0129_2(self) -> pd.DataFrame | None:
        """CR0129: Previously Paid - Fees must be numeric."""
        return self._numeric_present_rule("Previously Paid - Fees")

    @register_test(target_column="Reserve - Indemnity", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0130_2(self) -> pd.DataFrame | None:
        """CR0130: Reserve - Indemnity must be numeric."""
        return self._numeric_present_rule("Reserve - Indemnity")

    @register_test(target_column="Reserve - Fees", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0131_2(self) -> pd.DataFrame | None:
        """CR0131: Reserve - Fees must be numeric."""
        return self._numeric_present_rule("Reserve - Fees")

    @register_test(target_column="Total Incurred - Indemnity", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0134_2(self) -> pd.DataFrame | None:
        """CR0134: Total Incurred - Indemnity must be numeric."""
        return self._numeric_present_rule("Total Incurred - Indemnity")

    @register_test(target_column="Total Incurred - Fees", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0135_2(self) -> pd.DataFrame | None:
        """CR0135: Total Incurred - Fees must be numeric."""
        return self._numeric_present_rule("Total Incurred - Fees")

    @register_test(target_column="Date Claim First Advised/Date Claim Made", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0136_2(self) -> pd.DataFrame | None:
        """CR0136: Date Claim First Advised/Date Claim Made must be a valid date."""
        return self._date_rule("Date Claim First Advised/Date Claim Made")

    @register_test(target_column="Date Claim Opened", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0300_2(self) -> pd.DataFrame | None:
        """CR0300: Date Claim Opened must be a valid date."""
        return self._date_rule("Date Claim Opened")

    @register_test(target_column="Date of Loss (From)", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0119_2(self) -> pd.DataFrame | None:
        """CR0119: Date of Loss (From) must be a valid date."""
        return self._date_rule("Date of Loss (From)")

    @register_test(target_column="Date of Loss to", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0120_2(self) -> pd.DataFrame | None:
        """CR0120: Date of Loss to must be a valid date."""
        return self._date_rule("Date of Loss to")

    @register_test(target_column="Date Closed", severity=Severity.ERROR, test_type=TestType.DATA_TYPE)
    def test_CR0137_2(self) -> pd.DataFrame | None:
        """CR0137: Date Closed must be a valid date."""
        return self._date_rule("Date Closed")

    # ------------------------------------------------------------------
    # LOGIC checks
    # ------------------------------------------------------------------

    @register_test(target_column="Binding authority or coverholder appointment agreement expiry date", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0009_3(self) -> pd.DataFrame | None:
        """CR0009: Binding authority expiry date must be after the binding authority inception date."""
        return self._date_order_rule(
            "Binding authority or coverholder appointment agreement inception date",
            "Binding authority or coverholder appointment agreement expiry date",
        )

    @register_test(target_column="Binding authority or coverholder appointment agreement inception date", severity=Severity.WARNING, test_type=TestType.LOGIC)
    def test_CR0008_3(self) -> pd.DataFrame | None:
        """CR0008: Binding authority inception date must not be after the Reporting Period End Date."""
        return self._date_order_rule(
            "Binding authority or coverholder appointment agreement inception date",
            "Reporting Period (End Date)",
        )

    @register_test(target_column="Binding authority or coverholder appointment agreement expiry date", severity=Severity.WARNING, test_type=TestType.LOGIC)
    def test_CR0009_4(self) -> pd.DataFrame | None:
        """CR0009: Binding authority expiry date should not have expired more than 12 months before the Reporting Period End Date."""
        return self._date_not_older_than_months_rule(
            "Binding authority or coverholder appointment agreement expiry date",
            "Reporting Period (End Date)",
            months=12,
        )

    @register_test(target_column="Date Claim First Advised/Date Claim Made", severity=Severity.WARNING, test_type=TestType.LOGIC)
    def test_CR0136_3(self) -> pd.DataFrame | None:
        """CR0136: Date Claim First Advised must not be in the future."""
        return self._not_future_rule("Date Claim First Advised/Date Claim Made")

    @register_test(target_column="Date Claim Opened", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0300_3(self) -> pd.DataFrame | None:
        """CR0300: Date Claim Opened must be on or after Date Claim First Advised/Date Claim Made."""
        return self._date_order_rule(
            "Date Claim First Advised/Date Claim Made",
            "Date Claim Opened",
        )

    @register_test(target_column="Date of Loss (From)", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0119_3(self) -> pd.DataFrame | None:
        """CR0119: Date of Loss (From) must not be after Date Claim First Advised/Date Claim Made."""
        return self._date_order_rule(
            "Date of Loss (From)",
            "Date Claim First Advised/Date Claim Made",
        )

    @register_test(target_column="Date of Loss to", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0120_3(self) -> pd.DataFrame | None:
        """CR0120: Date of Loss to must be on or after Date of Loss (From)."""
        return self._date_order_rule("Date of Loss (From)", "Date of Loss to")

    @register_test(target_column="Date Closed", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0137_3(self) -> pd.DataFrame | None:
        """CR0137: Date Closed must be on or after Date Claim Opened."""
        return self._date_order_rule("Date Claim Opened", "Date Closed")

    @register_test(target_column="Total Incurred - Indemnity", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0134_3(self) -> pd.DataFrame | None:
        """CR0134: Total Incurred - Indemnity must equal Previously Paid - Indemnity + Paid this month - Indemnity + Reserve - Indemnity."""
        return self._arithmetic_check_rule(
            "Total Incurred - Indemnity",
            "Previously Paid - Indemnity",
            "Paid this month - Indemnity",
            "Reserve - Indemnity",
        )

    @register_test(target_column="Total Incurred - Fees", severity=Severity.ERROR, test_type=TestType.LOGIC)
    def test_CR0135_3(self) -> pd.DataFrame | None:
        """CR0135: Total Incurred - Fees must equal Previously Paid - Fees + Paid this month - Fees + Reserve - Fees."""
        return self._arithmetic_check_rule(
            "Total Incurred - Fees",
            "Previously Paid - Fees",
            "Paid this month - Fees",
            "Reserve - Fees",
        )
