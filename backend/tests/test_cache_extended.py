"""Expanded tests for the Cache service.

Tests edge cases: TTL, spot-price-based invalidation, reset,
and singleton contract.
"""

from unittest.mock import MagicMock

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

    def test_get_fresh_vs_get(self):
        """get() returns stale data within stale_ttl; get_if_fresh() checks TTL."""
        self.cache.set("gex:test", "data")
        # get_if_fresh respects per-key TTL; since we just set it, it's fresh
        assert self.cache.get_if_fresh("gex:test") == "data"

    def test_is_stale_fresh_key(self):
        """A newly set key should not be stale."""
        self.cache.set("gex:new", "val")
        assert self.cache.is_stale("gex:new") is False

    def test_is_stale_missing_key(self):
        """A missing key should be reported as stale."""
        assert self.cache.is_stale("gex:missing") is True

    def test_invalidate_removes_key(self):
        """invalidate() should remove a key and return True."""
        self.cache.set("gex:bye", "value")
        result = self.cache.invalidate("gex:bye")
        assert result is True
        assert self.cache.get("gex:bye") is None

    def test_invalidate_missing_key_returns_false(self):
        """invalidate() should return False for a key that never existed."""
        assert self.cache.invalidate("gex:ghost") is False


class TestGEXCacheSpotPriceInvalidation:
    """Test spot-price-based cache invalidation."""

    def setup_method(self):
        reset_cache()
        self.cache = get_cache()

    def test_update_spot_price_stores_in_spot_key(self):
        """update_spot_price() should store the value under 'spot:price'."""
        self.cache.update_spot_price(5900.0)
        assert self.cache.get("spot:price") == pytest.approx(5900.0)

    def test_update_spot_price_caches_last_price(self):
        """_last_spot_price should be updated."""
        self.cache.update_spot_price(5905.0)
        assert self.cache._last_spot_price == pytest.approx(5905.0)

    def test_large_move_triggers_invalidation(self):
        """A move > 1% should invalidate gex: keys."""
        mock_snapshot = MagicMock()
        self.cache.set("gex:current", mock_snapshot)
        assert self.cache.get("gex:current") is not None

        self.cache.update_spot_price(5900.0)
        # A 2% move exceeds the default 1% threshold
        self.cache.update_spot_price(5900.0 * 1.02)

        assert self.cache.get("gex:current") is None

    def test_small_move_does_not_invalidate(self):
        """A move < 1% should preserve the GEX cache."""
        mock_snapshot = MagicMock()
        self.cache.set("gex:current", mock_snapshot)

        self.cache.update_spot_price(5900.0)
        self.cache.update_spot_price(5900.5)  # ~0.008% move

        # GEX cache should still be present (within stale_ttl)
        assert self.cache.get("gex:current") is not None

    def test_invalidate_on_spot_move_returns_true_on_big_move(self):
        """invalidate_on_spot_move() should return True for large moves."""
        result = self.cache.invalidate_on_spot_move(5900.0, 6000.0)
        assert result is True

    def test_invalidate_on_spot_move_returns_false_on_small_move(self):
        """invalidate_on_spot_move() should return False for small moves."""
        result = self.cache.invalidate_on_spot_move(5900.0, 5901.0)
        assert result is False

    def test_symbol_scoped_spot_prices_do_not_overwrite_each_other(self):
        """Per-symbol spot keys should remain independent during watchlist capture."""
        self.cache.update_spot_price(5900.0, symbol="SPX")
        self.cache.update_spot_price(503.5, symbol="QQQ")

        assert self.cache.get("spot:price") == pytest.approx(5900.0)
        assert self.cache.get("spot:price:SPX") == pytest.approx(5900.0)
        assert self.cache.get("spot:price:QQQ") == pytest.approx(503.5)

    def test_large_move_invalidates_only_the_matching_symbol_cache(self):
        """A move in one symbol should not wipe cached snapshots for another symbol."""
        self.cache.set("gex:current:SPX", {"symbol": "SPX"})
        self.cache.set("gex:current:SPX:yfinance", {"symbol": "SPX"})
        self.cache.set("options:chain:SPX:today:yfinance", {"symbol": "SPX"})
        self.cache.set("gex:current:QQQ", {"symbol": "QQQ"})

        self.cache.update_spot_price(5900.0, symbol="SPX")
        self.cache.update_spot_price(6100.0, symbol="SPX")

        assert self.cache.get("gex:current:SPX") is None
        assert self.cache.get("gex:current:SPX:yfinance") is None
        assert self.cache.get("options:chain:SPX:today:yfinance") is None
        assert self.cache.get("gex:current:QQQ") == {"symbol": "QQQ"}


class TestGEXCacheClear:
    """Test cache clear and stats."""

    def test_clear_removes_all_entries(self):
        """clear() should wipe all cached data."""
        cache = GEXCache()
        cache.set("gex:1", "a")
        cache.set("gex:2", "b")
        n = cache.clear()
        assert n == 2
        assert cache.get("gex:1") is None

    def test_stats_returns_dict(self):
        """stats() should return a dict with entry counts."""
        cache = GEXCache()
        cache.set("gex:x", "val")
        stats = cache.stats()
        assert "total_entries" in stats
        assert "fresh_entries" in stats
        assert stats["total_entries"] >= 1

    def test_reset_cache_creates_new_instance(self):
        """reset_cache() should wipe the singleton so get_cache() returns a fresh one."""
        c1 = get_cache()
        c1.set("gex:foo", "bar")
        reset_cache()
        c2 = get_cache()
        assert c2.get("gex:foo") is None
        assert c1 is not c2


class TestGEXCacheSingleton:
    """Test get_cache() singleton behaviour."""

    def test_get_cache_returns_same_instance(self):
        """Multiple calls to get_cache() should return the same object."""
        reset_cache()
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2
