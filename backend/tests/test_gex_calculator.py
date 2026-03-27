"""0DTE GEX Backend - GEX Calculator Tests."""

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from app.core.gex_calculator import GEXCalculator
from app.core.constants import SPX_DIVIDEND_YIELD, RISK_FREE_RATE


ET = ZoneInfo("America/New_York")


@pytest.fixture
def sample_options_df() -> pd.DataFrame:
    """Create sample options chain DataFrame for testing."""
    # Current timestamp (2 hours to expiration)
    now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ET)
    expiration = "2024-01-15T16:00:00"

    data = [
        # Calls
        {"strike": 5700.0, "type": "call", "open_interest": 1000, "implied_vol": 0.20, "expiration": expiration},
        {"strike": 5750.0, "type": "call", "open_interest": 2000, "implied_vol": 0.18, "expiration": expiration},
        {"strike": 5800.0, "type": "call", "open_interest": 1500, "implied_vol": 0.17, "expiration": expiration},
        # Puts
        {"strike": 5700.0, "type": "put", "open_interest": 800, "implied_vol": 0.22, "expiration": expiration},
        {"strike": 5750.0, "type": "put", "open_interest": 1800, "implied_vol": 0.19, "expiration": expiration},
        {"strike": 5800.0, "type": "put", "open_interest": 1200, "implied_vol": 0.16, "expiration": expiration},
    ]

    return pd.DataFrame(data)


@pytest.fixture
def gex_calculator() -> GEXCalculator:
    """Create GEX calculator instance."""
    return GEXCalculator(
        risk_free_rate=RISK_FREE_RATE,
        dividend_yield=SPX_DIVIDEND_YIELD,
    )


class TestGEXCalculator:
    """Tests for GEX Calculator."""

    def test_calculate_gex_from_chain(self, sample_options_df, gex_calculator):
        """Test basic GEX calculation from options chain."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ET)
        spot_price = 5750.0

        result = gex_calculator.calculate_gex_from_chain(
            sample_options_df, spot_price, timestamp
        )

        # Verify structure
        assert result.timestamp == timestamp
        assert result.spot_price == spot_price
        assert isinstance(result.net_gex, float)
        assert isinstance(result.gex_by_strike, dict)
        assert len(result.gex_by_strike) == 3  # 3 unique strikes

        # Verify GEX signs
        # Call GEX should be negative (dealers short)
        assert result.total_call_gex < 0
        # Put GEX should be positive (dealers long)
        assert result.total_put_gex > 0

    def test_call_gex_negative_put_gex_positive(self, gex_calculator):
        """Verify dealer positioning: calls negative, puts positive."""
        # Simple chain with 1 call and 1 put
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ET)
        df = pd.DataFrame([
            {"strike": 5750.0, "type": "call", "open_interest": 1000, "implied_vol": 0.20, "expiration": "2024-01-15T16:00:00"},
            {"strike": 5750.0, "type": "put", "open_interest": 1000, "implied_vol": 0.20, "expiration": "2024-01-15T16:00:00"},
        ])

        result = gex_calculator.calculate_gex_from_chain(df, 5750.0, timestamp)

        assert result.total_call_gex < 0, "Call GEX should be negative"
        assert result.total_put_gex > 0, "Put GEX should be positive"

    def test_empty_dataframe_returns_zero_gex(self, gex_calculator):
        """Empty options chain should return zero GEX."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ET)
        empty_df = pd.DataFrame()

        result = gex_calculator.calculate_gex_from_chain(empty_df, 5750.0, timestamp)

        assert result.net_gex == 0.0
        assert result.total_call_gex == 0.0
        assert result.total_put_gex == 0.0
        assert result.gex_by_strike == {}

    def test_filter_zero_oi_contracts(self, gex_calculator):
        """Contracts with OI=0 should be filtered out."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ET)
        df = pd.DataFrame([
            {"strike": 5750.0, "type": "call", "open_interest": 0, "implied_vol": 0.20, "expiration": "2024-01-15T16:00:00"},
            {"strike": 5750.0, "type": "put", "open_interest": 1000, "implied_vol": 0.20, "expiration": "2024-01-15T16:00:00"},
        ])

        result = gex_calculator.calculate_gex_from_chain(df, 5750.0, timestamp)

        # Only put should contribute
        assert result.total_call_gex == 0.0
        assert result.total_put_gex > 0

    def test_filter_invalid_iv(self, gex_calculator):
        """Contracts with invalid IV should be filtered out."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ET)
        df = pd.DataFrame([
            {"strike": 5750.0, "type": "call", "open_interest": 1000, "implied_vol": 0.001, "expiration": "2024-01-15T16:00:00"},  # Too low
            {"strike": 5750.0, "type": "put", "open_interest": 1000, "implied_vol": 6.0, "expiration": "2024-01-15T16:00:00"},  # Too high
            {"strike": 5800.0, "type": "call", "open_interest": 1000, "implied_vol": 0.20, "expiration": "2024-01-15T16:00:00"},  # Valid
        ])

        result = gex_calculator.calculate_gex_from_chain(df, 5750.0, timestamp)

        # Only the valid contract should contribute
        assert len(result.gex_by_strike) == 1
        assert 5800.0 in result.gex_by_strike

    def test_same_day_date_only_expiration_uses_market_close(self, gex_calculator):
        """Date-only 0DTE expirations should retain time value until the close."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ET)
        df = pd.DataFrame([
            {"strike": 5750.0, "type": "call", "open_interest": 1000, "implied_vol": 0.20, "expiration": "2024-01-15"},
            {"strike": 5750.0, "type": "put", "open_interest": 1000, "implied_vol": 0.22, "expiration": "2024-01-15"},
        ])

        result = gex_calculator.calculate_gex_from_chain(df, 5750.0, timestamp)

        assert result.total_call_gex < 0
        assert result.total_put_gex > 0

    def test_zero_gamma_level_calculation(self, gex_calculator):
        """Test zero gamma level is between strikes."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ET)
        # Create chain where puts dominate below spot, calls dominate above
        df = pd.DataFrame([
            {"strike": 5700.0, "type": "put", "open_interest": 3000, "implied_vol": 0.20, "expiration": "2024-01-15T16:00:00"},
            {"strike": 5750.0, "type": "call", "open_interest": 3000, "implied_vol": 0.20, "expiration": "2024-01-15T16:00:00"},
        ])

        result = gex_calculator.calculate_gex_from_chain(df, 5725.0, timestamp)

        # Zero gamma level should be between the strikes
        assert 5700.0 <= result.zero_gamma_level <= 5750.0

    def test_zero_gamma_marks_below_range_when_no_crossing_exists(self, gex_calculator):
        """Purely positive cumulative GEX should be marked as below-range."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ET)
        df = pd.DataFrame([
            {"strike": 5700.0, "type": "put", "open_interest": 1000, "implied_vol": 0.20, "expiration": "2024-01-15T16:00:00"},
            {"strike": 5750.0, "type": "put", "open_interest": 1200, "implied_vol": 0.20, "expiration": "2024-01-15T16:00:00"},
            {"strike": 5800.0, "type": "put", "open_interest": 1400, "implied_vol": 0.20, "expiration": "2024-01-15T16:00:00"},
        ])

        result = gex_calculator.calculate_gex_from_chain(df, 5750.0, timestamp)

        assert result.zero_gamma_level == 5700.0
        assert result.metrics["zero_gamma_crossing_found"] is False
        assert result.metrics["zero_gamma_relation"] == "below_range"

    def test_zero_gamma_treats_near_zero_cumulative_value_as_exact_crossing(self, gex_calculator):
        """Floating-point residue near zero should still count as an in-range crossing."""
        zero_gamma_level, crossing_found, relation = gex_calculator._find_zero_gamma_level(
            {
                4000.0: 0.1,
                4100.0: 0.2,
                4200.0: -0.3,
            },
            spot_price=4100.0,
        )

        assert zero_gamma_level == 4200.0
        assert crossing_found is True
        assert relation == "in_range"

    def test_dominant_strike(self, sample_options_df, gex_calculator):
        """Test dominant strike is the one with highest absolute GEX."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ET)

        result = gex_calculator.calculate_gex_from_chain(
            sample_options_df, 5750.0, timestamp
        )

        # Dominant strike should have the highest absolute GEX
        max_abs_gex = max(abs(v) for v in result.gex_by_strike.values())
        assert abs(result.gex_by_strike[result.dominant_strike]) == max_abs_gex

    def test_metrics_included(self, sample_options_df, gex_calculator):
        """Test that metrics are calculated and included."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ET)

        result = gex_calculator.calculate_gex_from_chain(
            sample_options_df, 5750.0, timestamp
        )

        assert "gex_billions" in result.metrics
        assert "call_put_ratio" in result.metrics
        assert "regime_code" in result.metrics  # -1=short, 0=neutral, 1=long
        assert "num_strikes" in result.metrics


class TestRegimeDetermination:
    """Tests for regime determination."""

    def test_short_gamma_regime(self, gex_calculator):
        """Test short gamma regime detection."""
        regime, desc, color = gex_calculator.determine_regime(-2e9)  # -$2B

        assert regime == "short_gamma"
        assert color == "red"
        assert "short gamma" in desc.lower()

    def test_long_gamma_regime(self, gex_calculator):
        """Test long gamma regime detection."""
        regime, desc, color = gex_calculator.determine_regime(2e9)  # +$2B

        assert regime == "long_gamma"
        assert color == "green"
        assert "long gamma" in desc.lower()

    def test_neutral_regime(self, gex_calculator):
        """Test neutral regime detection."""
        regime, desc, color = gex_calculator.determine_regime(0.5e9)  # +$500M

        assert regime == "neutral"
        assert color == "yellow"


class TestGEXContribution:
    """Tests for GEX contribution analysis."""

    def test_gex_contribution_analysis(self, gex_calculator):
        """Test getting top contributing strikes."""
        gex_by_strike = {
            5700.0: -1e9,
            5725.0: -0.5e9,
            5750.0: 0.3e9,
            5775.0: 0.8e9,
            5800.0: 1.2e9,
        }

        result = gex_calculator.calculate_gex_contribution(
            gex_by_strike, spot_price=5750.0, n_top=3
        )

        assert "positive" in result
        assert "negative" in result
        assert len(result["negative"]) <= 3
        assert len(result["positive"]) <= 3
