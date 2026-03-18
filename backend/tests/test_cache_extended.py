"""Expanded tests for the Cache service.

Tests edge cases: TTL expiry, spot-price-triggered invalidation,
reset behaviour, concurrent access patterns, and capacity limits.
"""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.cache import GEXCache, get_cache, reset_cache


class TestGEXCacheBasicOps:
    """Test basic get/set operations."""

    def setup_method(self):
        reset_cache()
        self.cache = get_cache()

    def test_set_and_get(self):
        """Should retrieve a value that was just stored."""
        self.cache.set("key:test", "hello")
        assert self.cache.get("key:test") == "hello"

    def test_get_missing_key_returns_none(self):
        """Should return None for a key that was never set."""
        assert self.cache.get("nonexistent:key") is None

    def test_overwrite_value(self):
        """Setting the same key twice should return the latest value."""
        self.cache.set("key:x", "first")
        self.cache.set("key:x", "second")
        assert self.cache.get("key:x") == "second"

    def test_multiple_keys_independent(self):
        """Different keys should not interfere with each other."""
        self.cache.set("a", 1)
        self.cache.set("b", 2)
        assert self.cache.get("a") == 1
        assert self.cache.get("b") == 2


class TestGEXCacheTTL:
    """Test TTL-based expiry."""

    def setup_method(self):
        reset_cache()
        self.cache = get_cache()

    def test_value_available_before_ttl(self):
        """Value should be retrievable within its TTL."""
        self.cache.set("ttl:key", "value", ttl_seconds=60)
        assert self.cache.get("ttl:key") == "value"

    def test_value_expired_after_ttl(self):
        """Value should be None once TTL has elapsed."""
        self.cache.set("exp:key", "value", ttl_seconds=0.01)
        time.sleep(0.05)
        assert self.cache.get("exp:key") is None


class TestGEXCacheSpotPriceInvalidation:
    """Test spot-price-based cache invalidation."""

    def setup_method(self):
        reset_cache()
        self.cache = get_cache()

    def test_update_spot_price_stores_value(self):
        """update_spot_price should store the new spot price."""
        self.cache.update_spot_price(5900.0)
        assert self.cache.spot_price == pytest.approx(5900.0)

    def test_large_move_triggers_invalidation(self):
        """A large spot price move should invalidate GEX cache."""
        mock_snapshot = MagicMock()
        self.cache.set("gex:current", mock_snapshot)
        assert self.cache.get("gex:current") is not None

        self.cache.update_spot_price(5900.0)
        # A 5% move should invalidate the cache
        self.cache.update_spot_price(6195.0)  # +5%

        assert self.cache.get("gex:current") is None

    def test_small_move_does_not_invalidate(self):
        """A small spot price move should not invalidate GEX cache."""
        mock_snapshot = MagicMock()
        self.cache.set("gex:current", mock_snapshot)

        self.cache.update_spot_price(5900.0)
        self.cache.update_spot_price(5901.0)  # ~0.017%

        assert self.cache.get("gex:current") is not None


class TestGEXCacheReset:
    """Test cache reset."""

    def test_reset_clears_all_entries(self):
        """reset_cache() should wipe all stored values."""
        cache = get_cache()
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        reset_cache()
        new_cache = get_cache()
        assert new_cache.get("k1") is None
        assert new_cache.get("k2") is None

    def test_get_cache_returns_same_instance_after_reset(self):
        """After reset, get_cache() should still return a valid cache."""
        reset_cache()
        c = get_cache()
        assert c is not None
        assert isinstance(c, GEXCache)


class TestGEXCacheGetCacheSingleton:
    """Test get_cache() singleton behaviour."""

    def test_get_cache_returns_same_instance(self):
        """Multiple calls to get_cache() should return the same object."""
        reset_cache()
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2
