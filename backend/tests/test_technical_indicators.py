"""Tests for the pandas-ta technical indicator engine."""

import numpy as np
import pandas as pd
import pytest

from app.core.technical_indicators import TechnicalIndicatorEngine


def _make_price_df(n: int = 50) -> pd.DataFrame:
    """Create synthetic OHLCV price data."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="1D")
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n))
    low = close - np.abs(np.random.randn(n))
    open_ = close + np.random.randn(n) * 0.3
    volume = np.random.randint(1_000_000, 10_000_000, n)

    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=dates,
    )


class TestTechnicalIndicatorEngine:
    """Tests for the TechnicalIndicatorEngine."""

    def test_compute_all_indicators(self):
        """Should compute ATR, RSI, and BBANDS."""
        df = _make_price_df()
        result = TechnicalIndicatorEngine.compute_indicators(df)

        assert "atr" in result.columns
        assert "rsi" in result.columns
        assert "bb_upper" in result.columns
        assert "bb_mid" in result.columns
        assert "bb_lower" in result.columns

    def test_compute_single_indicator_atr(self):
        """Should compute only ATR when requested."""
        df = _make_price_df()
        result = TechnicalIndicatorEngine.compute_indicators(
            df, indicators=["ATR"]
        )

        assert "atr" in result.columns
        assert "rsi" not in result.columns
        assert "bb_upper" not in result.columns

    def test_compute_single_indicator_rsi(self):
        """Should compute only RSI when requested."""
        df = _make_price_df()
        result = TechnicalIndicatorEngine.compute_indicators(
            df, indicators=["RSI"]
        )

        assert "rsi" in result.columns
        assert "atr" not in result.columns

    def test_atr_values_positive(self):
        """ATR should be positive after warmup period."""
        df = _make_price_df()
        result = TechnicalIndicatorEngine.compute_indicators(
            df, indicators=["ATR"]
        )

        # After warmup, ATR should be positive
        atr_valid = result["atr"].dropna()
        assert len(atr_valid) > 0
        assert (atr_valid > 0).all()

    def test_rsi_values_bounded(self):
        """RSI should be between 0 and 100."""
        df = _make_price_df()
        result = TechnicalIndicatorEngine.compute_indicators(
            df, indicators=["RSI"]
        )

        rsi_valid = result["rsi"].dropna()
        assert len(rsi_valid) > 0
        assert (rsi_valid >= 0).all()
        assert (rsi_valid <= 100).all()

    def test_bbands_ordering(self):
        """BB Upper > BB Mid > BB Lower."""
        df = _make_price_df()
        result = TechnicalIndicatorEngine.compute_indicators(
            df, indicators=["BBANDS"]
        )

        valid = result.dropna(subset=["bb_upper", "bb_mid", "bb_lower"])
        if len(valid) > 0:
            assert (valid["bb_upper"] >= valid["bb_mid"]).all()
            assert (valid["bb_mid"] >= valid["bb_lower"]).all()

    def test_unsupported_indicator_raises(self):
        """Requesting an unsupported indicator should raise ValueError."""
        df = _make_price_df()
        with pytest.raises(ValueError, match="Unsupported indicators"):
            TechnicalIndicatorEngine.compute_indicators(
                df, indicators=["MACD"]
            )

    def test_missing_columns_raises(self):
        """Missing required columns should raise ValueError."""
        df = pd.DataFrame({"close": [1, 2, 3, 4, 5]})
        with pytest.raises(ValueError, match="Missing required columns"):
            TechnicalIndicatorEngine.compute_indicators(
                df, indicators=["ATR"]
            )

    def test_too_short_data_raises(self):
        """Too short data should raise ValueError."""
        df = _make_price_df(n=3)
        with pytest.raises(ValueError, match="at least 5"):
            TechnicalIndicatorEngine.compute_indicators(df)

    def test_custom_lengths(self):
        """Custom ATR/RSI/BB lengths should work."""
        df = _make_price_df(n=100)
        result = TechnicalIndicatorEngine.compute_indicators(
            df,
            indicators=["ATR", "RSI", "BBANDS"],
            atr_length=7,
            rsi_length=7,
            bb_length=10,
            bb_std=1.5,
        )

        assert "atr" in result.columns
        assert "rsi" in result.columns
        assert "bb_upper" in result.columns

    def test_lowercase_column_names(self):
        """Should handle already-lowercase column names."""
        df = _make_price_df()
        df.columns = [c.lower() for c in df.columns]
        result = TechnicalIndicatorEngine.compute_indicators(
            df, indicators=["RSI"]
        )
        assert "rsi" in result.columns
