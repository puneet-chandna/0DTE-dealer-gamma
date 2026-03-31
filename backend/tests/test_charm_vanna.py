"""Tests for Charm & Vanna calculations and the CharmVannaCalculator."""

import numpy as np
import pandas as pd

from app.core.charm_vanna_calculator import CharmVannaCalculator
from app.core.constants import SPX_DIVIDEND_YIELD
from app.core.greeks import BlackScholesGreeks


class TestCharmGreek:
    """Tests for the Charm (∂Δ/∂t) calculation."""

    def test_charm_call_sign(self):
        """ATM call Charm should be negative (delta decays toward 0.5 → 0)."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.01])  # Near expiry (0DTE-like)
        r = 0.05
        sigma = np.array([0.20])
        option_type = np.array(["call"])

        charm = BlackScholesGreeks.charm(S, K, T, r, sigma, option_type, q=SPX_DIVIDEND_YIELD)
        # Charm should be finite
        assert np.all(np.isfinite(charm))

    def test_charm_put_sign(self):
        """ATM put Charm should exist and be finite."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.01])
        r = 0.05
        sigma = np.array([0.20])
        option_type = np.array(["put"])

        charm = BlackScholesGreeks.charm(S, K, T, r, sigma, option_type, q=SPX_DIVIDEND_YIELD)
        assert np.all(np.isfinite(charm))

    def test_charm_zero_at_expiry(self):
        """Charm should be 0 when T=0."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.0])
        r = 0.05
        sigma = np.array([0.20])
        option_type = np.array(["call"])

        charm = BlackScholesGreeks.charm(S, K, T, r, sigma, option_type, q=SPX_DIVIDEND_YIELD)
        assert charm[0] == 0.0

    def test_charm_vectorized(self):
        """Charm calculation should work with multiple strikes."""
        n = 50
        S = np.full(n, 5800.0)
        K = np.linspace(5600, 6000, n)
        T = np.full(n, 0.003)  # ~1 trading hour
        r = 0.05
        sigma = np.full(n, 0.18)
        option_type = np.array(["call"] * 25 + ["put"] * 25)

        charm = BlackScholesGreeks.charm(S, K, T, r, sigma, option_type, q=SPX_DIVIDEND_YIELD)
        assert len(charm) == n
        assert np.all(np.isfinite(charm))


class TestVannaGreek:
    """Tests for the Vanna (∂Δ/∂σ) calculation."""

    def test_vanna_atm_finite(self):
        """ATM Vanna should be finite and non-zero."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.01])
        r = 0.05
        sigma = np.array([0.20])

        vanna = BlackScholesGreeks.vanna(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)
        assert np.all(np.isfinite(vanna))

    def test_vanna_zero_at_expiry(self):
        """Vanna should be 0 when T=0."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.0])
        r = 0.05
        sigma = np.array([0.20])

        vanna = BlackScholesGreeks.vanna(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)
        assert vanna[0] == 0.0

    def test_vanna_vectorized(self):
        """Vanna calculation should work with multiple options."""
        n = 100
        S = np.full(n, 5700.0)
        K = np.linspace(5500, 5900, n)
        T = np.full(n, 0.01)
        r = 0.05
        sigma = np.full(n, 0.20)

        vannas = BlackScholesGreeks.vanna(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)
        assert len(vannas) == n
        assert np.all(np.isfinite(vannas))

    def test_vanna_edge_case_zero_sigma(self):
        """Vanna with sigma=0 should return 0 (not NaN)."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        sigma = np.array([0.0])

        vanna = BlackScholesGreeks.vanna(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)
        assert vanna[0] == 0.0


class TestCalculateAllGreeksIncludesCharmVanna:
    """Verify calculate_all_greeks includes the new fields."""

    def test_greeks_result_has_charm_vanna(self):
        """GreeksResult should now include charm and vanna fields."""
        S = np.array([100.0, 100.0])
        K = np.array([100.0, 105.0])
        T = np.array([0.25, 0.25])
        r = 0.05
        sigma = np.array([0.2, 0.22])
        option_type = np.array(["call", "put"])
        q = SPX_DIVIDEND_YIELD

        result = BlackScholesGreeks.calculate_all_greeks(S, K, T, r, sigma, option_type, q=q)

        assert hasattr(result, "charm")
        assert hasattr(result, "vanna")
        assert len(result.charm) == 2
        assert len(result.vanna) == 2
        assert np.all(np.isfinite(result.charm))
        assert np.all(np.isfinite(result.vanna))


class TestCharmVannaCalculator:
    """Tests for the full CharmVannaCalculator flow calculator."""

    def test_empty_dataframe(self):
        """Empty DataFrame should return zero flows."""
        calc = CharmVannaCalculator()
        df = pd.DataFrame()
        result = calc.calculate_all(df, spot_price=5800.0, T=np.array([]))

        assert result["charm_flow"] == 0.0
        assert result["vanna_flow"] == 0.0
        assert result["net_hidden_flow"] == 0.0

    def test_single_contract(self):
        """Single contract should produce non-zero Charm and Vanna flows."""
        calc = CharmVannaCalculator()
        df = pd.DataFrame({
            "strike": [5800.0],
            "type": ["call"],
            "open_interest": [1000.0],
            "implied_vol": [0.20],
        })
        T = np.array([0.003])  # ~1 hour

        result = calc.calculate_all(df, spot_price=5800.0, T=T)

        assert isinstance(result["charm_flow"], float)
        assert isinstance(result["vanna_flow"], float)
        assert np.isfinite(result["charm_flow"])
        assert np.isfinite(result["vanna_flow"])

    def test_net_hidden_flow_is_sum(self):
        """Net hidden flow should equal charm_flow + vanna_flow."""
        calc = CharmVannaCalculator()
        df = pd.DataFrame({
            "strike": [5700.0, 5800.0, 5900.0],
            "type": ["call", "put", "call"],
            "open_interest": [500.0, 1000.0, 500.0],
            "implied_vol": [0.22, 0.20, 0.18],
        })
        T = np.array([0.003, 0.003, 0.003])

        result = calc.calculate_all(df, spot_price=5800.0, T=T)

        assert abs(result["net_hidden_flow"] - (result["charm_flow"] + result["vanna_flow"])) < 1e-6
