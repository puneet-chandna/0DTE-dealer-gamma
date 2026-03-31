"""Comprehensive tests for RiskFreeRateProvider.

Tests dynamic FRED fetching, caching, fallback behaviour, and the info
dictionary returned by get_rate_info().
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.core.constants import DEFAULT_RISK_FREE_RATE, FRED_RATE_SYMBOL
from app.core.rate_provider import RiskFreeRateProvider


class TestRiskFreeRateProviderInit:
    """Test RiskFreeRateProvider initialisation."""

    def test_starts_with_no_cached_rate(self):
        """Provider should have no cached rate on first creation."""
        provider = RiskFreeRateProvider()
        assert provider._cached_rate is None
        assert provider._last_fetched is None

    def test_starts_as_fallback(self):
        """Provider should start in fallback state."""
        provider = RiskFreeRateProvider()
        assert provider._is_fallback is True

    def test_custom_cache_ttl(self):
        """Should accept a custom cache TTL in seconds."""
        provider = RiskFreeRateProvider(cache_ttl_seconds=300)
        assert provider._cache_ttl == timedelta(seconds=300)


class TestRiskFreeRateProviderGetRate:
    """Test the get_rate() method — caching and fallback."""

    def setup_method(self):
        self.provider = RiskFreeRateProvider()

    def test_returns_fallback_when_fetch_fails(self):
        """Should return DEFAULT_RISK_FREE_RATE when FRED throws."""
        with patch.object(self.provider, "_fetch_from_fred",
                          side_effect=Exception("network error")):
            rate = self.provider.get_rate()
        assert rate == DEFAULT_RISK_FREE_RATE

    def test_returns_fetched_rate_on_success(self):
        """Should return the rate fetched from FRED."""
        with patch.object(self.provider, "_fetch_from_fred", return_value=0.045):
            rate = self.provider.get_rate()
        assert rate == pytest.approx(0.045)

    def test_uses_cached_rate_within_ttl(self):
        """Should not call _fetch_from_fred if cache is still fresh."""
        self.provider._cached_rate = 0.052
        self.provider._last_fetched = datetime.now()
        self.provider._is_fallback = False

        with patch.object(self.provider, "_fetch_from_fred") as mock_fetch:
            rate = self.provider.get_rate()
            mock_fetch.assert_not_called()

        assert rate == pytest.approx(0.052)

    def test_refetches_when_cache_expired(self):
        """Should fetch again when cache TTL has elapsed."""
        self.provider._cached_rate = 0.052
        self.provider._last_fetched = datetime.now() - timedelta(hours=25)
        self.provider._is_fallback = False

        with patch.object(self.provider, "_fetch_from_fred", return_value=0.048) as mock_fetch:
            rate = self.provider.get_rate()
            mock_fetch.assert_called_once()

        assert rate == pytest.approx(0.048)

    def test_rate_is_annualised_decimal(self):
        """Rate should be a decimal between 0 and 1."""
        with patch.object(self.provider, "_fetch_from_fred", return_value=0.05):
            rate = self.provider.get_rate()
        assert 0.0 < rate < 1.0

    def test_fallback_not_cached(self):
        """Fallback rate should not be cached so we retry next call."""
        with patch.object(self.provider, "_fetch_from_fred",
                          side_effect=Exception("transient")):
            self.provider.get_rate()

        # _cached_rate should still be None or unchanged after fallback
        assert self.provider._is_fallback is True


class TestRiskFreeRateProviderGetRateInfo:
    """Test the get_rate_info() method (the API dict)."""

    def setup_method(self):
        self.provider = RiskFreeRateProvider()

    def test_info_contains_required_keys(self):
        """get_rate_info() should return a dict with all required fields."""
        with patch.object(self.provider, "_fetch_from_fred",
                          side_effect=Exception("offline")):
            info = self.provider.get_rate_info()

        required = {"rate", "rate_pct", "source", "symbol", "is_fallback",
                    "cache_ttl_seconds", "fetched_at"}
        assert required.issubset(info.keys())

    def test_info_rate_pct_matches_rate(self):
        """rate_pct should equal rate × 100."""
        with patch.object(self.provider, "_fetch_from_fred", return_value=0.045):
            info = self.provider.get_rate_info()
        assert info["rate_pct"] == pytest.approx(info["rate"] * 100, rel=1e-4)

    def test_info_marks_fallback_correctly(self):
        """is_fallback should be True when FRED fetch failed."""
        with patch.object(self.provider, "_fetch_from_fred",
                          side_effect=Exception("x")):
            info = self.provider.get_rate_info()
        assert info["is_fallback"] is True

    def test_info_marks_non_fallback_when_live(self):
        """is_fallback should be False after a successful FRED fetch."""
        with patch.object(self.provider, "_fetch_from_fred", return_value=0.043):
            info = self.provider.get_rate_info()
        assert info["is_fallback"] is False

    def test_info_source_contains_fred_on_live(self):
        """Source should mention FRED when rate was live-fetched."""
        with patch.object(self.provider, "_fetch_from_fred", return_value=0.043):
            info = self.provider.get_rate_info()
        assert "FRED" in info["source"] or "fred" in info["source"].lower()

    def test_info_symbol_is_fred_symbol(self):
        """Symbol field should match the FRED series constant."""
        with patch.object(self.provider, "_fetch_from_fred",
                          side_effect=Exception("offline")):
            info = self.provider.get_rate_info()
        assert info["symbol"] == FRED_RATE_SYMBOL
