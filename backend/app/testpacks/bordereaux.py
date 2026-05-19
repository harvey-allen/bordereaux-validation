from __future__ import annotations

import pandas as pd

from app.testpacks.core import BaseTestPack, Severity, register_pack, register_test


@register_pack("bordereaux")
class BordereauxTestPack(BaseTestPack):
    """
    Test pack for bordereaux validation.
    
    Severity levels affect heatmap intensity:
    - INFO (1): Minor issues, light coloring
    - WARNING (2): Moderate issues, medium coloring  
    - ERROR (3): Serious issues, strong coloring
    - CRITICAL (5): Critical issues, maximum coloring
    
    Tests can target one or multiple columns using:
    - target_column="field_name" for a single field
    - target_columns=["field1", "field2"] for multiple fields
    """

    def _select_columns(self, *columns: str) -> pd.DataFrame:
        """Helper to select columns including trans_ref without duplicates."""
        cols = list(dict.fromkeys([self.trans_ref] + list(columns)))
        return self._df[cols].copy()

    @register_test(
        target_column="policy_id",
        severity=Severity.CRITICAL,
    )
    def test_policy_id_required(self) -> pd.DataFrame | None:
        """Policy ID must be populated for all records."""
        if "policy_id" not in self._df.columns:
            return None
        
        data = self._select_columns("policy_id")
        policy_col = self._df["policy_id"]
        data["test_results"] = policy_col.notna() & (policy_col.astype(str).str.strip() != "")
        return data[[self.trans_ref, "test_results"]]

    @register_test(
        target_column="premium_amount",
        severity=Severity.ERROR,
    )
    def test_premium_amount_required(self) -> pd.DataFrame | None:
        """Premium amount must be populated and positive."""
        if "premium_amount" not in self._df.columns:
            return None
        
        data = self._select_columns("premium_amount")
        premium_col = pd.to_numeric(self._df["premium_amount"], errors="coerce")
        data["test_results"] = premium_col.notna() & (premium_col > 0)
        return data[[self.trans_ref, "test_results"]]

    @register_test(
        target_column="currency",
        severity=Severity.ERROR,
    )
    def test_currency_valid(self) -> pd.DataFrame | None:
        """Currency must be a valid ISO 4217 code (GBP, USD, EUR)."""
        if "currency" not in self._df.columns:
            return None
        
        valid_currencies = {"GBP", "USD", "EUR", "JPY", "CHF", "CAD", "AUD", "NZD"}
        data = self._select_columns("currency")
        data["test_results"] = self._df["currency"].isin(valid_currencies)
        return data[[self.trans_ref, "test_results"]]

    @register_test(
        target_columns=["product_type", "vessel_id"],
        severity=Severity.WARNING,
    )
    def test_marine_requires_vessel(self) -> pd.DataFrame | None:
        """Marine policies must have a vessel ID."""
        if "product_type" not in self._df.columns or "vessel_id" not in self._df.columns:
            return None
        
        # Only test marine policies
        marine_mask = self._df["product_type"].astype(str).str.upper() == "MARINE"
        data = self._df.loc[marine_mask, [self.trans_ref]].copy()
        
        if data.empty:
            return None
        
        vessel_col = self._df.loc[marine_mask, "vessel_id"]
        data["test_results"] = vessel_col.notna() & (vessel_col.astype(str).str.strip() != "")
        return data[[self.trans_ref, "test_results"]]

    @register_test(
        target_columns=["claim_amount", "policy_limit"],
        severity=Severity.CRITICAL,
    )
    def test_claim_within_limit(self) -> pd.DataFrame | None:
        """Claim amount must not exceed policy limit."""
        if "claim_amount" not in self._df.columns or "policy_limit" not in self._df.columns:
            return None
        
        # Convert to numeric
        claim_col = pd.to_numeric(self._df["claim_amount"], errors="coerce")
        limit_col = pd.to_numeric(self._df["policy_limit"], errors="coerce")
        
        # Only test rows with claims
        has_claim = claim_col.notna() & (claim_col > 0)
        data = self._df.loc[has_claim, [self.trans_ref]].copy()
        
        if data.empty:
            return None
        
        data["test_results"] = claim_col[has_claim] <= limit_col[has_claim]
        return data[[self.trans_ref, "test_results"]]
