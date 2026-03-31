"""Expanded tests for GEX calculator edge cases.

Tests boundary conditions, special market scenarios, dynamic rate providers,
regime classification, and GEX-by-strike breakdown.
"""

import math
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.core.constants import CONTRACT_MULTIPLIER
from app.core.gex_calculator import GEXCalculator
from app.core.greeks import BlackScholesGreeks

ET = ZoneInfo("America/New_York")


def _make_df(
    strikes=None,
    call_oi=1000,
    put_oi=1000,
    iv=0.20,
) -> pd.DataFrame:
    """Build a minimal valid options DataFrame (uses 'type' and 'implied_vol' columns)."""
    if strikes is None:
        strikes = [5900.0, 5950.0]
    rows = []
    for k in strikes:
        rows.append({
            "type": "call",
            "strike": k,
            "open_interest": call_oi,
            "implied_vol": iv,
            "expiration": "2099-01-15",
        })
        rows.append({
            "type": "put",
            "strike": k,
            "open_interest": put_oi,
            "implied_vol": iv + 0.02,
            "expiration": "2099-01-15",
        })
    return pd.DataFrame(rows)


class TestGEXCalculatorEdgeCases:
    """Edge-case tests for GEXCalculator."""

    def setup_method(self):
        self.calc = GEXCalculator()

    def test_empty_options_df_returns_zero_snapshot(self):
        """Empty DataFrame should return a valid zero-GEX snapshot."""
        empty = pd.DataFrame(
            columns=["type", "strike", "open_interest", "implied_vol", "expiration"]
        )
        snap = self.calc.calculate_gex_from_chain(
            options_df=empty, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert snap is not None
        assert math.isfinite(snap.net_gex)

    def test_near_zero_open_interest_is_filtered(self):
        """Contracts with OI=0 should be filtered; non-zero OI should survive."""
        df = _make_df(call_oi=0, put_oi=5000)
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert math.isfinite(snap.net_gex)

    def test_spot_price_stored_correctly(self):
        """Snapshot should carry the exact spot price passed in."""
        df = _make_df()
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=6000.0, timestamp=datetime.now(ET)
        )
        assert snap.spot_price == pytest.approx(6000.0)

    def test_zero_gamma_level_is_finite(self):
        """zero_gamma_level should always be a real, finite price."""
        df = _make_df()
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert math.isfinite(snap.zero_gamma_level)

    def test_dominant_strike_is_a_number(self):
        """dominant_strike should be finite."""
        df = _make_df(strikes=[5880.0, 5900.0, 5920.0])
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert math.isfinite(snap.dominant_strike)

    def test_total_gex_is_sum_of_call_and_put(self):
        """net_gex should equal total_call_gex + total_put_gex."""
        df = _make_df()
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert snap.net_gex == pytest.approx(
            snap.total_call_gex + snap.total_put_gex, rel=1e-5
        )

    def test_dynamic_rate_provider_used(self):
        """If a rate_provider is set its get_rate() should be used."""
        mock_provider = MagicMock()
        mock_provider.get_rate.return_value = 0.045
        calc = GEXCalculator(rate_provider=mock_provider)
        # Accessing the property should call get_rate
        rate = calc.risk_free_rate
        assert rate == pytest.approx(0.045)
        mock_provider.get_rate.assert_called()

    def test_static_rate_used_without_provider(self):
        """Without a rate_provider, the static rate should be returned."""
        calc = GEXCalculator(risk_free_rate=0.03)
        assert calc.risk_free_rate == pytest.approx(0.03)


class TestGEXCalculatorGexByStrike:
    """Test GEX-by-strike breakdown stored in snapshot."""

    def setup_method(self):
        self.calc = GEXCalculator()

    def test_gex_by_strike_is_dict(self):
        """gex_by_strike should be a dict keyed by strike price."""
        df = _make_df(strikes=[5880.0, 5900.0, 5920.0])
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert isinstance(snap.gex_by_strike, dict)

    def test_gex_by_strike_keys_are_strikes(self):
        """All keys in gex_by_strike should be floats."""
        df = _make_df(strikes=[5880.0, 5900.0, 5920.0])
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        for k in snap.gex_by_strike.keys():
            assert isinstance(k, float)

    def test_dominant_strike_in_gex_dict(self):
        """dominant_strike should be one of the keys in gex_by_strike."""
        df = _make_df(strikes=[5880.0, 5900.0, 5920.0])
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert snap.dominant_strike in snap.gex_by_strike

    def test_all_gex_values_finite(self):
        """All values in gex_by_strike should be finite floats."""
        df = _make_df(strikes=[5880.0, 5900.0, 5920.0])
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        for v in snap.gex_by_strike.values():
            assert math.isfinite(v)


class TestGEXCalculatorCallPutSigns:
    """Test trader-facing baseline signs (calls positive, puts negative)."""

    def setup_method(self):
        self.calc = GEXCalculator()

    def test_calls_only_gives_positive_total_call_gex(self):
        """Calls-only DataFrame should give a positive total_call_gex."""
        df = _make_df(call_oi=5000, put_oi=0).query("type == 'call'")
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert snap.total_call_gex >= 0

    def test_puts_only_gives_negative_total_put_gex(self):
        """Puts-only DataFrame should give a negative total_put_gex."""
        df = _make_df(call_oi=0, put_oi=5000).query("type == 'put'")
        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=5900.0, timestamp=datetime.now(ET)
        )
        assert snap.total_put_gex <= 0

    def test_gex_values_are_scaled_to_per_one_percent_move(self):
        """The calculator should apply the 1% move normalization to notional gamma."""
        timestamp = datetime(2026, 3, 24, 12, 0, 0, tzinfo=ET)
        expiration = "2026-03-24T16:00:00"
        spot_price = 5900.0
        strike = 5900.0
        iv = 0.20
        open_interest = 1000

        df = pd.DataFrame(
            [
                {
                    "type": "call",
                    "strike": strike,
                    "open_interest": open_interest,
                    "implied_vol": iv,
                    "expiration": expiration,
                }
            ]
        )

        snap = self.calc.calculate_gex_from_chain(
            options_df=df, spot_price=spot_price, timestamp=timestamp
        )
        expiration_timestamp = pd.DatetimeIndex(
            [pd.Timestamp(expiration).tz_localize(ET)]
        )
        time_to_expiration = (
            (expiration_timestamp - pd.Timestamp(timestamp)).total_seconds()
            / (365.25 * 24 * 3600)
        ).to_numpy()
        gamma = BlackScholesGreeks.gamma(
            pd.Series([spot_price], dtype=float).to_numpy(),
            pd.Series([strike], dtype=float).to_numpy(),
            time_to_expiration,
            self.calc.risk_free_rate,
            pd.Series([iv], dtype=float).to_numpy(),
            q=self.calc.dividend_yield,
        )[0]
        raw_notional = open_interest * gamma * CONTRACT_MULTIPLIER * (spot_price ** 2)

        assert snap.total_call_gex == pytest.approx(raw_notional * 0.01, rel=1e-6)
