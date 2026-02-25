"""Tests for the py_vollib bridge — Greeks cross-validation and IV surface."""

import numpy as np
import pytest

from app.core.vollib_bridge import VolLibBridge
from app.core.constants import SPX_DIVIDEND_YIELD


class TestGreeksCrossValidation:
    """Verify our Black-Scholes Greeks match py_vollib within tolerance."""

    def test_call_delta_cross_validation(self):
        """Call delta from our BS and py_vollib should be close."""
        result = VolLibBridge.validate_greeks(
            S=100.0, K=100.0, T=0.25, r=0.05, sigma=0.20, q=0.0
        )
        diff = result["call"]["diff"]["delta"]
        assert diff < 0.05, f"Call delta diff too large: {diff}"

    def test_put_delta_cross_validation(self):
        """Put delta from our BS and py_vollib should be close."""
        result = VolLibBridge.validate_greeks(
            S=100.0, K=100.0, T=0.25, r=0.05, sigma=0.20, q=0.0
        )
        diff = result["put"]["diff"]["delta"]
        assert diff < 0.05, f"Put delta diff too large: {diff}"

    def test_gamma_cross_validation(self):
        """Gamma from both implementations should match closely."""
        result = VolLibBridge.validate_greeks(
            S=100.0, K=100.0, T=0.25, r=0.05, sigma=0.20, q=0.0
        )
        # Gamma is same for calls and puts
        diff = result["call"]["diff"]["gamma"]
        assert diff < 0.005, f"Gamma diff too large: {diff}"

    def test_vega_cross_validation(self):
        """Vega from both implementations should be in the same ballpark."""
        result = VolLibBridge.validate_greeks(
            S=100.0, K=100.0, T=0.25, r=0.05, sigma=0.20, q=0.0
        )
        # Vega normalization differs (per 1% vs raw), so allow wider tolerance
        diff = result["call"]["diff"]["vega"]
        assert diff < 0.25, f"Vega diff too large: {diff}"

    def test_cross_validation_with_dividend(self):
        """Cross-validation should work with dividend yield too."""
        result = VolLibBridge.validate_greeks(
            S=5900.0, K=5900.0, T=1 / 365, r=0.05, sigma=0.20,
            q=SPX_DIVIDEND_YIELD,
        )
        # With dividend adjustment, differences may be slightly larger
        for opt_type in ["call", "put"]:
            for greek in ["delta", "gamma"]:
                diff = result[opt_type]["diff"][greek]
                assert diff < 0.1, (
                    f"{opt_type} {greek} diff too large with dividend: {diff}"
                )

    def test_cross_validation_otm(self):
        """OTM options should still have reasonable cross-validation."""
        result = VolLibBridge.validate_greeks(
            S=100.0, K=120.0, T=0.25, r=0.05, sigma=0.30, q=0.0
        )
        # OTM delta should be small but match
        assert result["call"]["our"]["delta"] < 0.3
        assert result["call"]["diff"]["delta"] < 0.05


class TestIVSurface:
    """Test IV surface and skew computation."""

    def _make_options_df(self):
        """Create a synthetic options DataFrame."""
        import pandas as pd

        data = []
        for strike in [95, 97, 100, 103, 105]:
            for opt_type in ["call", "put"]:
                # Simple intrinsic + time value pricing
                if opt_type == "call":
                    mid = max(100 - strike, 0) + 2.0
                else:
                    mid = max(strike - 100, 0) + 2.0
                data.append({
                    "strike": float(strike),
                    "type": opt_type,
                    "mid": mid,
                    "T": 30 / 365,  # 30 days to expiry
                })

        return pd.DataFrame(data)

    def test_iv_surface_returns_dataframe(self):
        """IV surface should return a DataFrame."""
        df = self._make_options_df()
        result = VolLibBridge.calculate_iv_surface(df, spot_price=100.0, r=0.05)
        assert len(result) > 0
        assert "iv" in result.columns
        assert "strike" in result.columns

    def test_iv_surface_reasonable_values(self):
        """IVs should be in a reasonable range."""
        df = self._make_options_df()
        result = VolLibBridge.calculate_iv_surface(df, spot_price=100.0, r=0.05)
        if not result.empty:
            assert result["iv"].min() > 0
            assert result["iv"].max() < 5.0

    def test_iv_skew_computation(self):
        """IV skew should be computable from surface."""
        df = self._make_options_df()
        surface = VolLibBridge.calculate_iv_surface(df, spot_price=100.0, r=0.05)
        skew = VolLibBridge.calculate_iv_skew(surface)
        if not skew.empty:
            assert "skew" in skew.columns
            assert "call_iv" in skew.columns
            assert "put_iv" in skew.columns

    def test_iv_surface_empty_input(self):
        """Empty options DataFrame should return empty surface."""
        import pandas as pd

        empty = pd.DataFrame(columns=["strike", "type", "mid", "T"])
        result = VolLibBridge.calculate_iv_surface(empty, spot_price=100.0)
        assert result.empty

    def test_iv_skew_empty_input(self):
        """Empty surface should return empty skew."""
        import pandas as pd

        empty = pd.DataFrame(columns=["strike", "type", "iv", "mid_price", "moneyness"])
        result = VolLibBridge.calculate_iv_skew(empty)
        assert result.empty
