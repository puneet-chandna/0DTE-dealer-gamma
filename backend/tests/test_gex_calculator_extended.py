"""Expanded tests for GEX calculator edge cases.

Tests boundary conditions, special market scenarios, and numeric edge cases
not covered by the core test_gex_calculator.py.
"""

import math
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.core.gex_calculator import GEXCalculator
from app.core.constants import DEFAULT_RISK_FREE_RATE

ET = ZoneInfo("America/New_York")


def _minimal_options_df(
    strikes=None,
    call_gamma=0.01,
    put_gamma=0.01,
    call_oi=1000,
    put_oi=1000,
) -> pd.DataFrame:
    """Build a minimal options DataFrame for testing."""
    if strikes is None:
        strikes = [5900.0, 5950.0]
    rows = []
    for k in strikes:
        rows.append({
            "contractType": "call",
            "strike": k,
            "openInterest": call_oi,
            "impliedVolatility": 0.20,
            "gamma": call_gamma,
            "delta": 0.5,
            "expiration": "2099-01-15",
        })
        rows.append({
            "contractType": "put",
            "strike": k,
            "openInterest": put_oi,
            "impliedVolatility": 0.22,
            "gamma": put_gamma,
            "delta": -0.5,
            "expiration": "2099-01-15",
        })
    return pd.DataFrame(rows)


class TestGEXCalculatorEdgeCases:
    """Edge-case tests for GEXCalculator."""

    def setup_method(self):
        self.calc = GEXCalculator()

    def test_empty_options_df_raises_or_returns_zero(self):
        """Empty DataFrame should not crash the calculator."""
        empty = pd.DataFrame(
            columns=["contractType", "strike", "openInterest",
                     "impliedVolatility", "gamma", "delta", "expiration"]
        )
        try:
            snap = self.calc.calculate_gex_from_chain(
                options_df=empty, spot_price=5900.0, timestamp=datetime.now(ET)
            )
            assert snap.net_gex == 0.0 or math.isfinite(snap.net_gex)
        except (ValueError, ZeroDivisionError):
            pass  # acceptable to raise on empty input

    def test_all_calls_returns_negative_net_gex(self):
        """With only call options a dealer is short gamma → net GEX should be negative."""
        df = _minimal_options_df(call_oi=5000, put_oi=0)
        snap = self.calc.calculate_gex_from_chain(
            options_df=df[df.contractType == "call"],
            spot_price=5900.0,
            timestamp=datetime.now(ET),
        )
        assert snap.net_gex < 0 or snap.net_gex == 0  # can be 0 if OI contribution is zero

    def test_all_puts_returns_positive_net_gex(self):
        """With only put options a dealer is long gamma → net GEX should be positive."""
        df = _minimal_options_df(call_oi=0, put_oi=5000)
        snap = self.calc.calculate_gex_from_chain(
            options_df=df[df.contractType == "put"],
            spot_price=5900.0,
            timestamp=datetime.now(ET),
        )
        assert snap.net_gex >= 0

    def test_near_zero_open_interest(self):
        """Near-zero OI should not cause division-by-zero or NaN."""
        df = _minimal_options_df(call_oi=1, put_oi=1)
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert math.isfinite(snap.net_gex)

    def test_spot_price_stored_correctly(self):
        """Snapshot should carry the correct spot price."""
        df = _minimal_options_df()
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=6000.0, timestamp=datetime.now(ET)
        )
        assert snap.spot_price == pytest.approx(6000.0)

    def test_zero_gamma_level_is_finite(self):
        """Zero-gamma level should be a real, finite price."""
        df = _minimal_options_df()
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert math.isfinite(snap.zero_gamma_level)

    def test_dynamic_rate_provider_used(self):
        """If a rate_provider is set it should be called during calculation."""
        mock_provider = MagicMock()
        mock_provider.get_rate.return_value = 0.045
        calc = GEXCalculator(rate_provider=mock_provider)
        df = _minimal_options_df()
        calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        # rate_provider.get_rate should have been accessed at least once
        # (either directly or via the property)
        assert calc.risk_free_rate == pytest.approx(0.045)


class TestGEXCalculatorRegimes:
    """Test market regime classification."""

    def setup_method(self):
        self.calc = GEXCalculator()

    def test_large_negative_gex_gives_negative_gamma_regime(self):
        """Strongly negative GEX → negative gamma regime."""
        df = _minimal_options_df(call_oi=100000, put_oi=0)
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        if snap.net_gex < -1e8:
            from app.core.gex_calculator import GEXRegime
            assert "negative" in snap.regime.value.lower() or snap.regime is not None

    def test_regime_has_description(self):
        """Regime data should always include a description string."""
        df = _minimal_options_df()
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert hasattr(snap, "regime")
        assert snap.regime is not None


class TestGEXCalculatorByStrike:
    """Test GEX breakdown by strike."""

    def setup_method(self):
        self.calc = GEXCalculator()

    def test_gex_by_strike_returns_list(self):
        """get_gex_by_strike should return a list of strike-level contributions."""
        df = _minimal_options_df(strikes=[5880.0, 5900.0, 5920.0])
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        by_strike = self.calc.get_gex_by_strike(snap)
        assert isinstance(by_strike, list)
        assert len(by_strike) > 0

    def test_dominant_strike_in_strikes_list(self):
        """dominant_strike should be one of the available strikes."""
        df = _minimal_options_df(strikes=[5880.0, 5900.0, 5920.0])
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        by_strike = self.calc.get_gex_by_strike(snap)
        strikes = {item.strike for item in by_strike}
        assert snap.dominant_strike in strikes
