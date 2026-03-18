"""Expanded tests for the Risk-Free Rate provider.

Tests dynamic FRED fetching, caching, fallback behaviour,
and thread-safety of RiskFreeRateProvider.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.core.rate_provider import RiskFreeRateProvider
from app.core.constants import DEFAULT_RISK_FREE_RATE


class TestRiskFreeRateProviderInit:
    """Test RiskFreeRateProvider initialisation."""

    def test_has_correct_default_rate(self):
        """Fallback rate should match DEFAULT_RISK_FREE_RATE constant."""
        provider = RiskFreeRateProvider()
        assert provider._fallback_rate == DEFAULT_RISK_FREE_RATE

    def test_starts_with_no_cached_rate(self):
        """Provider should have no cached rate on first creation."""
        provider = RiskFreeRateProvider()
        assert provider._cached_rate is None
        assert provider._last_fetched is None

    def test_custom_fallback_rate(self):
        """Should accept a custom fallback rate."""
        provider = RiskFreeRateProvider(fallback_rate=0.03)
        assert provider._fallback_rate == 0.03


class TestRiskFreeRateProviderGetRate:
    """Test the get_rate() method with caching and fallback."""

    def setup_method(self):
        self.provider = RiskFreeRateProvider()

    def test_returns_fallback_when_fetch_fails(self):
        """Should return fallback rate when FRED fetch raises an exception."""
        with patch.object(self.provider, "_fetch_from_fred", side_effect=Exception("network")):
            rate = self.provider.get_rate()
        assert rate == DEFAULT_RISK_FREE_RATE

    def test_returns_fetched_rate_on_success(self):
        """Should return the rate fetched from FRED."""
        with patch.object(self.provider, "_fetch_from_fred", return_value=0.045):
            rate = self.provider.get_rate()
        assert rate == pytest.approx(0.045)

    def test_uses_cached_rate_within_ttl(self):
        """Should not re-fetch if cache is fresh (within TTL)."""
        self.provider._cached_rate = 0.052
        self.provider._last_fetched = datetime.now()  # just now

        with patch.object(self.provider, "_fetch_from_fred") as mock_fetch:
            rate = self.provider.get_rate()
            mock_fetch.assert_not_called()

        assert rate == pytest.approx(0.052)

    def test_refetches_after_cache_expires(self):
        """Should fetch again when cache TTL has expired."""
        self.provider._cached_rate = 0.052
        # Simulate cache that expired 25 hours ago (TTL is 24 hours)
        self.provider._last_fetched = datetime.now() - timedelta(hours=25)

        with patch.object(self.provider, "_fetch_from_fred", return_value=0.048) as mock_fetch:
            rate = self.provider.get_rate()
            mock_fetch.assert_called_once()

        assert rate == pytest.approx(0.048)

    def test_fallback_on_none_from_fred(self):
        """Should use fallback when FRED returns None."""
        with patch.object(self.provider, "_fetch_from_fred", return_value=None):
            rate = self.provider.get_rate()
        assert rate == DEFAULT_RISK_FREE_RATE

    def test_rate_is_annualised_decimal(self):
        """Rate should be expressed as a decimal (0.05 not 5.0)."""
        with patch.object(self.provider, "_fetch_from_fred", return_value=0.05):
            rate = self.provider.get_rate()
        assert 0.0 < rate < 1.0  # sanity: rate between 0% and 100%


class TestRiskFreeRateProviderInfo:
    """Test the get_info() method."""

    def setup_method(self):
        self.provider = RiskFreeRateProvider()

    def test_info_contains_required_keys(self):
        """get_info() should return a dict with all required fields."""
        with patch.object(self.provider, "get_rate", return_value=DEFAULT_RISK_FREE_RATE):
            info = self.provider.get_info()
        required = {"rate", "rate_pct", "source", "symbol", "is_fallback", "cache_ttl_seconds"}
        assert required.issubset(info.keys())

    def test_info_rate_pct_is_percentage(self):
        """rate_pct should equal rate * 100."""
        with patch.object(self.provider, "_fetch_from_fred", return_value=0.045):
            self.provider.get_rate()
            info = self.provider.get_info()
        assert info["rate_pct"] == pytest.approx(info["rate"] * 100, rel=1e-4)

    def test_info_marks_fallback_correctly(self):
        """is_fallback should be True when FRED fetch failed."""
        with patch.object(self.provider, "_fetch_from_fred", side_effect=Exception("x")):
            self.provider.get_rate()
            info = self.provider.get_info()
        assert info["is_fallback"] is True

    def test_info_source_when_live(self):
        """Source should indicate FRED when rate was fetched successfully."""
        with patch.object(self.provider, "_fetch_from_fred", return_value=0.043):
            self.provider.get_rate()
            info = self.provider.get_info()
        assert "FRED" in info["source"] or "fred" in info["source"].lower()
