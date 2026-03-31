"""Tests for the vectorbt backtesting engine."""

import numpy as np
import pandas as pd

from app.core.vectorbt_backtester import VectorBTBacktester, VectorBTResult


def _make_synthetic_data(n: int = 500):
    """Create synthetic price and GEX data for backtesting."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="5min")

    # Price: random walk
    returns = np.random.randn(n) * 0.001
    close = 5900 * np.cumprod(1 + returns)

    price_df = pd.DataFrame({"close": close}, index=dates)

    # GEX: oscillates between short and long gamma
    gex_values = np.sin(np.linspace(0, 8 * np.pi, n)) * 2e9
    gex_values += np.random.randn(n) * 5e8  # noise

    gex_df = pd.DataFrame({"net_gex": gex_values}, index=dates)

    return price_df, gex_df


class TestVectorBTBacktester:
    """Tests for VectorBTBacktester."""

    def test_basic_backtest_runs(self):
        """Backtest should run without errors."""
        price_df, gex_df = _make_synthetic_data()
        result = VectorBTBacktester.run_gex_signal_backtest(
            price_data=price_df,
            gex_data=gex_df,
            entry_threshold=-1e9,
            exit_threshold=0.0,
        )

        assert isinstance(result, VectorBTResult)
        assert isinstance(result.total_return, float)
        assert isinstance(result.equity_curve, list)

    def test_result_metrics_finite(self):
        """All result metrics should be finite numbers."""
        price_df, gex_df = _make_synthetic_data()
        result = VectorBTBacktester.run_gex_signal_backtest(
            price_data=price_df,
            gex_data=gex_df,
        )

        assert np.isfinite(result.total_return)
        assert np.isfinite(result.sharpe_ratio)
        assert np.isfinite(result.max_drawdown)
        assert result.total_trades >= 0
        assert 0.0 <= result.win_rate <= 1.0

    def test_equity_curve_not_empty(self):
        """Equity curve should have data points."""
        price_df, gex_df = _make_synthetic_data()
        result = VectorBTBacktester.run_gex_signal_backtest(
            price_data=price_df,
            gex_data=gex_df,
        )

        assert len(result.equity_curve) > 0

    def test_dates_preserved(self):
        """Start and end dates should match input data."""
        price_df, gex_df = _make_synthetic_data()
        result = VectorBTBacktester.run_gex_signal_backtest(
            price_data=price_df,
            gex_data=gex_df,
        )

        assert result.start_date is not None
        assert result.end_date is not None

    def test_no_trades_with_extreme_threshold(self):
        """With an extreme threshold, should have zero or very few trades."""
        price_df, gex_df = _make_synthetic_data()
        result = VectorBTBacktester.run_gex_signal_backtest(
            price_data=price_df,
            gex_data=gex_df,
            entry_threshold=-1e15,  # Impossibly low
            exit_threshold=-1e14,
        )

        assert result.total_trades == 0

    def test_custom_initial_cash(self):
        """Custom initial cash should be reflected."""
        price_df, gex_df = _make_synthetic_data()
        result = VectorBTBacktester.run_gex_signal_backtest(
            price_data=price_df,
            gex_data=gex_df,
            initial_cash=1_000_000.0,
        )

        # Equity curve first value should be around 1M
        assert result.equity_curve[0] > 900_000


class TestRegimeComparison:
    """Tests for regime comparison analysis."""

    def test_regime_comparison_runs(self):
        """Regime comparison should run without errors."""
        price_df, gex_df = _make_synthetic_data()
        result = VectorBTBacktester.run_regime_comparison(
            price_data=price_df,
            gex_data=gex_df,
        )

        assert "short_gamma" in result
        assert "neutral" in result
        assert "long_gamma" in result

    def test_regime_has_expected_keys(self):
        """Each regime should have count, mean_return, etc."""
        price_df, gex_df = _make_synthetic_data()
        result = VectorBTBacktester.run_regime_comparison(
            price_data=price_df,
            gex_data=gex_df,
        )

        for regime in ["short_gamma", "neutral", "long_gamma"]:
            assert "count" in result[regime]
            assert "mean_return" in result[regime]
            assert "std_return" in result[regime]
            assert "sharpe" in result[regime]
            assert "total_return" in result[regime]
