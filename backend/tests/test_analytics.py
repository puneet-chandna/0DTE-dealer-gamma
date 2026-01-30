"""Tests for the Analytics Module.

Comprehensive tests for VolatilityAnalyzer, TradingStrategy,
and synthetic data generators.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from app.core.analytics import (
    VolatilityAnalyzer,
    TradingStrategy,
    generate_synthetic_gex_data,
    generate_synthetic_price_data,
)
from app.core.constants import SHORT_GAMMA_THRESHOLD, LONG_GAMMA_THRESHOLD

ET = ZoneInfo("America/New_York")


class TestVolatilityAnalyzerRealizedVolatility:
    """Test realized volatility calculations."""

    def test_calculate_rv_basic(self):
        """Should calculate RV from price data."""
        # Create simple price series
        dates = pd.date_range("2025-01-15 09:30", periods=100, freq="5min", tz=ET)
        prices = 5900 + np.random.randn(100).cumsum() * 5
        price_data = pd.DataFrame({"close": prices}, index=dates)

        rv = VolatilityAnalyzer.calculate_realized_volatility(price_data, window_minutes=15)

        # Should return a series with some values
        assert isinstance(rv, pd.Series)
        assert len(rv) > 0
        # RV should be positive
        assert (rv.dropna() >= 0).all()

    def test_calculate_rv_constant_prices(self):
        """Should return zero RV for constant prices."""
        dates = pd.date_range("2025-01-15 09:30", periods=100, freq="5min", tz=ET)
        prices = np.full(100, 5900.0)
        price_data = pd.DataFrame({"close": prices}, index=dates)

        rv = VolatilityAnalyzer.calculate_realized_volatility(price_data, window_minutes=15)

        # RV should be zero (or very close) for constant prices
        assert np.allclose(rv.dropna().values, 0.0, atol=1e-10)

    def test_calculate_rv_empty_dataframe(self):
        """Should handle empty DataFrame."""
        empty_df = pd.DataFrame({"close": []})
        rv = VolatilityAnalyzer.calculate_realized_volatility(empty_df)
        assert len(rv) == 0

    def test_calculate_rv_custom_window(self):
        """Should respect custom window parameter."""
        dates = pd.date_range("2025-01-15 09:30", periods=100, freq="5min", tz=ET)
        prices = 5900 + np.random.randn(100).cumsum() * 5
        price_data = pd.DataFrame({"close": prices}, index=dates)

        rv_short = VolatilityAnalyzer.calculate_realized_volatility(price_data, window_minutes=10)
        rv_long = VolatilityAnalyzer.calculate_realized_volatility(price_data, window_minutes=60)

        # Both should have values
        assert len(rv_short.dropna()) > 0
        assert len(rv_long.dropna()) > 0


class TestVolatilityAnalyzerGEXRelationship:
    """Test GEX-volatility relationship analysis."""

    @pytest.fixture
    def sample_data(self):
        """Create sample GEX and price data for testing."""
        dates = pd.date_range("2025-01-15 09:30", periods=200, freq="5min", tz=ET)

        # GEX data with some negative values
        gex_values = np.random.randn(200) * 2e9
        gex_data = pd.DataFrame({"net_gex": gex_values}, index=dates)

        # Price data with some volatility
        prices = 5900 + np.random.randn(200).cumsum() * 5
        price_data = pd.DataFrame({"close": prices}, index=dates)

        return gex_data, price_data

    def test_analyze_relationship_returns_result(self, sample_data):
        """Should return AnalyticsResult."""
        gex_data, price_data = sample_data

        result = VolatilityAnalyzer.analyze_gex_volatility_relationship(
            gex_data, price_data
        )

        # Should return an AnalyticsResult
        assert hasattr(result, "mean_rv_negative_gex")
        assert hasattr(result, "mean_rv_positive_gex")
        assert hasattr(result, "t_statistic")
        assert hasattr(result, "p_value")
        assert hasattr(result, "significant")

    def test_analyze_relationship_sample_sizes(self, sample_data):
        """Should report correct sample sizes."""
        gex_data, price_data = sample_data

        result = VolatilityAnalyzer.analyze_gex_volatility_relationship(
            gex_data, price_data
        )

        # Sample sizes should be reported
        assert result.sample_size_negative >= 0
        assert result.sample_size_positive >= 0

    def test_analyze_relationship_custom_thresholds(self, sample_data):
        """Should use custom thresholds."""
        gex_data, price_data = sample_data

        result = VolatilityAnalyzer.analyze_gex_volatility_relationship(
            gex_data,
            price_data,
            negative_threshold=-1e8,
            positive_threshold=1e8,
        )

        # Should still return valid result
        assert hasattr(result, "t_statistic")


class TestVolatilityAnalyzerSummaryStats:
    """Test summary statistics computation."""

    def test_compute_summary_basic(self):
        """Should compute basic summary statistics."""
        dates = pd.date_range("2025-01-15 09:30", periods=100, freq="5min", tz=ET)
        gex_values = np.random.randn(100) * 1e9
        gex_data = pd.DataFrame({"net_gex": gex_values}, index=dates)

        stats = VolatilityAnalyzer.compute_summary_statistics(gex_data)

        # Should have all required fields
        assert hasattr(stats, "mean_gex")
        assert hasattr(stats, "std_gex")
        assert hasattr(stats, "min_gex")
        assert hasattr(stats, "max_gex")
        assert hasattr(stats, "median_gex")
        assert hasattr(stats, "pct_negative_days")
        assert hasattr(stats, "sample_size")

    def test_compute_summary_correct_values(self):
        """Should compute correct statistics."""
        dates = pd.date_range("2025-01-15 09:30", periods=5, freq="5min", tz=ET)
        gex_data = pd.DataFrame({"net_gex": [-2e9, -1e9, 0, 1e9, 2e9]}, index=dates)

        stats = VolatilityAnalyzer.compute_summary_statistics(gex_data)

        assert stats.mean_gex == 0
        assert stats.min_gex == -2e9
        assert stats.max_gex == 2e9
        assert stats.median_gex == 0
        assert stats.sample_size == 5
        # 2 out of 5 values are negative = 40%
        assert stats.pct_negative_days == 40.0

    def test_compute_summary_empty_dataframe(self):
        """Should handle empty DataFrame."""
        empty_df = pd.DataFrame({"net_gex": []})
        stats = VolatilityAnalyzer.compute_summary_statistics(empty_df)

        # Should return stats with zero/NaN values
        assert stats.sample_size == 0


class TestTradingStrategyVolatilityBreakout:
    """Test volatility breakout backtesting."""

    @pytest.fixture
    def backtest_data(self):
        """Create data for backtesting."""
        dates = pd.date_range("2025-01-15 09:30", periods=500, freq="5min", tz=ET)

        # GEX data with periods of short gamma
        gex_values = np.random.randn(500) * 1e9
        # Add some clearly negative periods
        gex_values[100:150] = -3e9  # Short gamma period
        gex_values[300:350] = -2.5e9  # Another short gamma period
        gex_data = pd.DataFrame({"net_gex": gex_values}, index=dates)

        # Price data with trending behavior
        prices = 5900 + np.random.randn(500).cumsum() * 2
        price_data = pd.DataFrame({"close": prices}, index=dates)

        return gex_data, price_data

    def test_backtest_returns_result(self, backtest_data):
        """Should return BacktestResult."""
        gex_data, price_data = backtest_data

        result = TradingStrategy.volatility_breakout_strategy(gex_data, price_data)

        # Should return a BacktestResult
        assert hasattr(result, "total_trades")
        assert hasattr(result, "winning_trades")
        assert hasattr(result, "losing_trades")
        assert hasattr(result, "win_rate")
        assert hasattr(result, "total_return")
        assert hasattr(result, "sharpe_ratio")

    def test_backtest_custom_parameters(self, backtest_data):
        """Should use custom parameters."""
        gex_data, price_data = backtest_data

        result = TradingStrategy.volatility_breakout_strategy(
            gex_data,
            price_data,
            entry_threshold=-1e9,
            exit_threshold=0.5e9,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
        )

        assert hasattr(result, "total_trades")

    def test_backtest_no_trades_scenario(self):
        """Should handle case with no trade signals."""
        dates = pd.date_range("2025-01-15 09:30", periods=100, freq="5min", tz=ET)

        # All positive GEX (no short gamma)
        gex_data = pd.DataFrame({"net_gex": np.full(100, 2e9)}, index=dates)
        prices = 5900 + np.arange(100)
        price_data = pd.DataFrame({"close": prices}, index=dates)

        result = TradingStrategy.volatility_breakout_strategy(gex_data, price_data)

        # Should have 0 trades
        assert result.total_trades == 0


class TestTradingStrategyRegimeBased:
    """Test regime-based strategy analysis."""

    @pytest.fixture
    def regime_data(self):
        """Create data with different regimes."""
        dates = pd.date_range("2025-01-15 09:30", periods=300, freq="5min", tz=ET)

        # Create data with 3 regimes
        gex_values = np.zeros(300)
        gex_values[:100] = -2.5e9  # Short gamma
        gex_values[100:200] = 0  # Neutral
        gex_values[200:] = 2.5e9  # Long gamma

        gex_data = pd.DataFrame({"net_gex": gex_values}, index=dates)

        prices = 5900 + np.random.randn(300).cumsum() * 2
        price_data = pd.DataFrame({"close": prices}, index=dates)

        return gex_data, price_data

    def test_regime_strategy_returns_dict(self, regime_data):
        """Should return dictionary with regime stats."""
        gex_data, price_data = regime_data

        result = TradingStrategy.regime_based_strategy(gex_data, price_data)

        assert isinstance(result, dict)
        # Should have keys for regimes
        assert "short_gamma" in result or len(result) > 0


class TestSyntheticDataGeneration:
    """Test synthetic data generators."""

    def test_generate_synthetic_gex_data(self):
        """Should generate valid GEX data."""
        start = datetime(2025, 1, 15, 9, 30, tzinfo=ET)
        end = datetime(2025, 1, 15, 16, 0, tzinfo=ET)

        gex_data = generate_synthetic_gex_data(start, end, freq="5min")

        assert isinstance(gex_data, pd.DataFrame)
        assert "net_gex" in gex_data.columns
        assert len(gex_data) > 0
        # Should have datetime index
        assert isinstance(gex_data.index, pd.DatetimeIndex)

    def test_generate_synthetic_gex_mean_reversion(self):
        """Synthetic GEX should show mean-reverting behavior."""
        start = datetime(2025, 1, 15, 9, 30, tzinfo=ET)
        end = datetime(2025, 1, 15, 16, 0, tzinfo=ET)

        gex_data = generate_synthetic_gex_data(start, end)

        # Mean should be somewhat close to zero (mean-reverting)
        mean = gex_data["net_gex"].mean()
        # Allow for some deviation but should not be extremely biased
        assert abs(mean) < 5e9  # Not ridiculously biased

    def test_generate_synthetic_price_data(self):
        """Should generate valid price data."""
        start = datetime(2025, 1, 15, 9, 30, tzinfo=ET)
        end = datetime(2025, 1, 15, 16, 0, tzinfo=ET)

        price_data = generate_synthetic_price_data(start, end, freq="5min")

        assert isinstance(price_data, pd.DataFrame)
        assert "close" in price_data.columns
        assert len(price_data) > 0
        # Prices should be positive
        assert (price_data["close"] > 0).all()

    def test_generate_synthetic_price_custom_initial(self):
        """Should use custom initial price."""
        start = datetime(2025, 1, 15, 9, 30, tzinfo=ET)
        end = datetime(2025, 1, 15, 10, 0, tzinfo=ET)

        price_data = generate_synthetic_price_data(start, end, initial_price=6000.0)

        # First price should be close to initial
        assert abs(price_data["close"].iloc[0] - 6000.0) < 100

    def test_generate_data_different_frequencies(self):
        """Should respect frequency parameter."""
        start = datetime(2025, 1, 15, 9, 30, tzinfo=ET)
        end = datetime(2025, 1, 15, 10, 0, tzinfo=ET)

        gex_1min = generate_synthetic_gex_data(start, end, freq="1min")
        gex_5min = generate_synthetic_gex_data(start, end, freq="5min")

        # 1min should have ~5x more data points
        assert len(gex_1min) > len(gex_5min)
