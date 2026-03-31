"""Tests for the Cache Service.

Comprehensive tests for the GEXCache class covering TTL, invalidation,
and cache statistics.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.services.cache import GEXCache, get_cache, reset_cache


class TestGEXCacheBasicOperations:
    """Test basic cache get/set operations."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache instance."""
        return GEXCache()

    def test_set_and_get(self, cache):
        """Should store and retrieve a value."""
        cache.set("test:key", {"value": 123})
        result = cache.get("test:key")
        assert result == {"value": 123}

    def test_get_missing_key(self, cache):
        """Should return None for missing key."""
        result = cache.get("nonexistent:key")
        assert result is None

    def test_set_overwrites(self, cache):
        """Should overwrite existing value."""
        cache.set("test:key", "first")
        cache.set("test:key", "second")
        result = cache.get("test:key")
        assert result == "second"

    def test_stores_complex_objects(self, cache):
        """Should store complex nested objects."""
        data = {
            "gex": -1500000000,
            "strikes": [5800, 5850, 5900],
            "nested": {"level1": {"level2": "value"}},
        }
        cache.set("complex:data", data)
        result = cache.get("complex:data")
        assert result == data


class TestGEXCacheTTL:
    """Test TTL behavior."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache instance."""
        return GEXCache()

    def test_get_ttl_gex_prefix(self, cache):
        """Should return GEX TTL for gex: prefix."""
        ttl = cache._get_ttl("gex:current")
        assert ttl.total_seconds() == 5

    def test_get_ttl_spot_prefix(self, cache):
        """Should return spot TTL for spot: prefix."""
        ttl = cache._get_ttl("spot:price")
        assert ttl.total_seconds() == 1

    def test_get_ttl_options_prefix(self, cache):
        """Should return options TTL for options: prefix."""
        ttl = cache._get_ttl("options:chain:2025-01-15")
        assert ttl.total_seconds() == 30

    def test_get_ttl_analytics_prefix(self, cache):
        """Should return analytics TTL for analytics: prefix."""
        ttl = cache._get_ttl("analytics:summary")
        assert ttl.total_seconds() == 300  # 5 minutes

    def test_get_ttl_default(self, cache):
        """Should return default TTL for unknown prefix."""
        ttl = cache._get_ttl("unknown:key")
        assert ttl.total_seconds() == 5  # default is GEX_CACHE_TTL

    def test_is_stale_missing_key(self, cache):
        """Missing key should be considered stale."""
        assert cache.is_stale("missing:key") is True

    def test_is_stale_fresh_key(self, cache):
        """Fresh key should not be stale."""
        cache.set("gex:current", {"data": 1})
        assert cache.is_stale("gex:current") is False

    def test_is_stale_after_ttl(self, cache):
        """Key should be stale after TTL."""
        # Patch datetime to simulate time passing
        now = datetime.now()
        with patch("app.services.cache.datetime") as mock_dt:
            mock_dt.now.return_value = now
            cache.set("spot:price", 5900.0)

            # Move time forward past TTL (1 second for spot)
            mock_dt.now.return_value = now + timedelta(seconds=2)
            assert cache.is_stale("spot:price") is True

    def test_get_if_fresh_returns_data(self, cache):
        """get_if_fresh should return data when fresh."""
        cache.set("gex:current", {"net_gex": -1000})
        result = cache.get_if_fresh("gex:current")
        assert result == {"net_gex": -1000}

    def test_get_if_fresh_returns_none_when_stale(self, cache):
        """get_if_fresh should return None when stale."""
        now = datetime.now()
        with patch("app.services.cache.datetime") as mock_dt:
            mock_dt.now.return_value = now
            cache.set("spot:price", 5900.0)

            # Move time past TTL
            mock_dt.now.return_value = now + timedelta(seconds=5)
            assert cache.get_if_fresh("spot:price") is None

    def test_get_removes_very_stale_data(self, cache):
        """get should remove data older than stale TTL (1 hour)."""
        now = datetime.now()
        with patch("app.services.cache.datetime") as mock_dt:
            mock_dt.now.return_value = now
            cache.set("old:data", "value")

            # Move time past stale TTL (1 hour)
            mock_dt.now.return_value = now + timedelta(hours=2)
            result = cache.get("old:data")
            assert result is None
            # Key should be deleted
            assert "old:data" not in cache._cache


class TestGEXCacheInvalidation:
    """Test cache invalidation methods."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache instance."""
        return GEXCache()

    def test_invalidate_existing_key(self, cache):
        """Should invalidate and return True for existing key."""
        cache.set("test:key", "value")
        result = cache.invalidate("test:key")
        assert result is True
        assert cache.get("test:key") is None

    def test_invalidate_missing_key(self, cache):
        """Should return False for missing key."""
        result = cache.invalidate("missing:key")
        assert result is False

    def test_invalidate_prefix(self, cache):
        """Should invalidate all keys matching prefix."""
        cache.set("gex:current", 1)
        cache.set("gex:strikes:2025-01-15", 2)
        cache.set("gex:another", 3)
        cache.set("other:key", 4)

        count = cache.invalidate_prefix("gex:")
        assert count == 3
        assert cache.get("gex:current") is None
        assert cache.get("other:key") == 4

    def test_invalidate_prefix_no_matches(self, cache):
        """Should return 0 if no keys match prefix."""
        cache.set("other:key", 1)
        count = cache.invalidate_prefix("gex:")
        assert count == 0


class TestGEXCacheSpotInvalidation:
    """Test spot-price-based cache invalidation."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache instance."""
        return GEXCache()

    def test_no_invalidation_on_small_move(self, cache):
        """Should not invalidate for small spot moves (<1%)."""
        cache.set("gex:current", {"data": 1})
        result = cache.invalidate_on_spot_move(5900.0, 5910.0)  # ~0.17% move
        assert result is False
        assert cache.get("gex:current") == {"data": 1}

    def test_invalidation_on_large_move(self, cache):
        """Should invalidate GEX and options caches for large spot moves (>1%)."""
        cache.set("gex:current", {"data": 1})
        cache.set("options:chain", {"data": 2})
        cache.set("analytics:summary", {"data": 3})

        result = cache.invalidate_on_spot_move(5900.0, 6000.0)  # ~1.7% move
        assert result is True
        assert cache.get("gex:current") is None
        assert cache.get("options:chain") is None
        # Analytics should still exist
        assert cache.get("analytics:summary") == {"data": 3}

    def test_no_invalidation_zero_old_spot(self, cache):
        """Should return False if old_spot is zero (prevent division by zero)."""
        cache.set("gex:current", {"data": 1})
        result = cache.invalidate_on_spot_move(0.0, 5900.0)
        assert result is False

    def test_custom_threshold(self, cache):
        """Should use custom threshold percentage."""
        cache.set("gex:current", {"data": 1})
        # 0.5% move with 0.01% threshold should invalidate
        result = cache.invalidate_on_spot_move(5900.0, 5930.0, threshold_pct=0.001)
        assert result is True

    def test_update_spot_price_caches_and_checks(self, cache):
        """update_spot_price should cache price and check invalidation."""
        cache.set("gex:current", {"data": 1})

        # First update - no previous price
        invalidated = cache.update_spot_price(5900.0)
        assert invalidated is False
        assert cache.get("spot:price") == 5900.0

        # Second update - small move
        invalidated = cache.update_spot_price(5910.0)
        assert invalidated is False

        # Third update - large move
        invalidated = cache.update_spot_price(6100.0)  # >1% move
        assert invalidated is True


class TestGEXCacheStats:
    """Test cache statistics."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache instance."""
        return GEXCache()

    def test_stats_empty_cache(self, cache):
        """Should return correct stats for empty cache."""
        stats = cache.stats()
        assert stats["total_entries"] == 0
        assert stats["fresh_entries"] == 0
        assert stats["stale_entries"] == 0
        assert stats["last_spot_price"] is None
        assert stats["keys"] == []

    def test_stats_with_entries(self, cache):
        """Should return correct stats with entries."""
        cache.set("gex:current", 1)
        cache.set("spot:price", 5900.0)
        cache._last_spot_price = 5900.0

        stats = cache.stats()
        assert stats["total_entries"] == 2
        assert stats["fresh_entries"] == 2
        assert stats["last_spot_price"] == 5900.0
        assert "gex:current" in stats["keys"]
        assert "spot:price" in stats["keys"]

    def test_stats_with_stale_entries(self, cache):
        """Should count stale entries correctly."""
        now = datetime.now()
        with patch("app.services.cache.datetime") as mock_dt:
            mock_dt.now.return_value = now
            cache.set("spot:price", 5900.0)  # TTL = 1s

            # Move time past spot TTL but before gex TTL
            mock_dt.now.return_value = now + timedelta(seconds=3)
            cache.set("gex:current", 1)  # Fresh, TTL = 5s

            stats = cache.stats()
            assert stats["total_entries"] == 2
            assert stats["fresh_entries"] == 1
            assert stats["stale_entries"] == 1


class TestGEXCacheClear:
    """Test cache clear operations."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache instance."""
        return GEXCache()

    def test_clear_empty_cache(self, cache):
        """Should return 0 for empty cache."""
        count = cache.clear()
        assert count == 0

    def test_clear_removes_all(self, cache):
        """Should remove all entries."""
        cache.set("key1", 1)
        cache.set("key2", 2)
        cache.set("key3", 3)
        cache._last_spot_price = 5900.0

        count = cache.clear()
        assert count == 3
        assert len(cache._cache) == 0
        assert cache._last_spot_price is None


class TestGlobalCacheInstance:
    """Test global cache singleton functions."""

    def setup_method(self):
        """Reset cache before each test."""
        reset_cache()

    def teardown_method(self):
        """Reset cache after each test."""
        reset_cache()

    def test_get_cache_creates_instance(self):
        """get_cache should create a new instance if none exists."""
        cache = get_cache()
        assert isinstance(cache, GEXCache)

    def test_get_cache_returns_same_instance(self):
        """get_cache should return the same instance."""
        cache1 = get_cache()
        cache2 = get_cache()
        assert cache1 is cache2

    def test_reset_cache_clears_and_removes(self):
        """reset_cache should clear and remove the instance."""
        cache = get_cache()
        cache.set("test:key", "value")

        reset_cache()

        # New instance should be created
        new_cache = get_cache()
        assert new_cache.get("test:key") is None
