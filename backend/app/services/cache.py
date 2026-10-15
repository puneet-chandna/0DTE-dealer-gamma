"""0DTE GEX Backend - In-Memory Cache Service with TTL.

Provides caching for GEX calculations, spot prices, and options chain data
to reduce API calls and improve response times.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, TypeVar

from app.core.constants import (
    ANALYTICS_CACHE_TTL,
    GEX_CACHE_TTL,
    OPTIONS_CHAIN_CACHE_TTL,
    SPOT_CACHE_TTL,
)
from app.core.data_acquisition import get_current_trading_date

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GEXCache:
    """In-memory cache with TTL for GEX snapshots and related data.

    Cache Keys and TTLs:
    - gex:current         -> 5s   (GEX snapshot)
    - gex:strikes:{date}  -> 5s   (Strike breakdown)
    - spot:price          -> 1s   (Current spot price)
    - options:chain:{date}-> 30s  (Raw options chain)
    - analytics:summary   -> 5min (Analytics results)

    Attributes:
        _cache: Internal storage dict mapping keys to (stored_at, data) tuples.
        _ttl_config: Mapping of cache key prefixes to TTL timedelta.
    """

    def __init__(self) -> None:
        """Initialize empty cache with TTL configuration."""
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._last_spot_price: float | None = None
        self._last_spot_prices: dict[str, float] = {}
        self._inflight: dict[str, tuple[asyncio.Future, int]] = {}

        # TTL configuration by key prefix
        self._ttl_config: dict[str, timedelta] = {
            "gex:": timedelta(seconds=GEX_CACHE_TTL),
            "spot:": timedelta(seconds=SPOT_CACHE_TTL),
            "options:": timedelta(seconds=OPTIONS_CHAIN_CACHE_TTL),
            "analytics:": timedelta(seconds=ANALYTICS_CACHE_TTL),
        }

        # Default TTL for unmatched keys
        self._default_ttl = timedelta(seconds=GEX_CACHE_TTL)

        # Stale data TTL (max age before deletion)
        self._stale_ttl = timedelta(hours=1)

    def _get_ttl(self, key: str) -> timedelta:
        """Get TTL for a cache key based on its prefix.

        Args:
            key: Cache key.

        Returns:
            TTL for this key type.
        """
        for prefix, ttl in self._ttl_config.items():
            if key.startswith(prefix):
                return ttl
        return self._default_ttl

    def get(self, key: str) -> Any | None:
        """Get value from cache if not stale.

        Args:
            key: Cache key to retrieve.

        Returns:
            Cached value if exists and not too stale, None otherwise.
        """
        if key not in self._cache:
            return None

        stored_at, data = self._cache[key]
        age = datetime.now() - stored_at

        # Delete if older than stale TTL
        if age > self._stale_ttl:
            del self._cache[key]
            logger.debug(f"Cache key '{key}' deleted (stale)")
            return None

        return data

    def get_if_fresh(self, key: str) -> Any | None:
        """Get value only if it's within TTL (not stale).

        Args:
            key: Cache key to retrieve.

        Returns:
            Cached value if exists and fresh, None otherwise.
        """
        if key not in self._cache:
            return None

        stored_at, data = self._cache[key]
        age = datetime.now() - stored_at
        ttl = self._get_ttl(key)

        if age > ttl:
            return None

        return data

    def set(self, key: str, data: Any) -> None:
        """Store value in cache with current timestamp.

        Args:
            key: Cache key.
            data: Data to cache.
        """
        self._cache[key] = (datetime.now(), data)
        logger.debug(f"Cache set: '{key}'")

    async def fetch_once(self, key: str, fetch: Callable[[], Awaitable[T]]) -> T:
        """Share an in-flight fetch; each waiter receives its own mutable result."""
        if key not in self._inflight:
            task = asyncio.ensure_future(fetch())
            # Retrieve late errors if every waiter has already canceled.
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            self._inflight[key] = (task, 0)
        task, waiters = self._inflight[key]
        self._inflight[key] = (task, waiters + 1)
        try:
            return deepcopy(await asyncio.shield(task))
        finally:
            _, waiters = self._inflight[key]
            if waiters == 1:
                del self._inflight[key]
                if not task.done():
                    task.cancel()
            else:
                self._inflight[key] = (task, waiters - 1)

    async def fetch_gex_chain(self, client, symbol: str = "SPX"):
        """Coalesce all GEX producers without sharing their calculation or persistence."""
        symbol = self._normalize_symbol(symbol)
        session_date = get_current_trading_date().isoformat()
        return await self.fetch_once(
            f"fetch:gex:{symbol}:{client.provider_name}:{session_date}",
            lambda: client.get_options_chain_for_gex(underlying=symbol),
        )

    def is_stale(self, key: str) -> bool:
        """Check if cache entry is stale (beyond TTL).

        Args:
            key: Cache key to check.

        Returns:
            True if key doesn't exist or is stale, False if fresh.
        """
        if key not in self._cache:
            return True

        stored_at, _ = self._cache[key]
        age = datetime.now() - stored_at
        ttl = self._get_ttl(key)

        return age > ttl

    def invalidate(self, key: str) -> bool:
        """Remove a specific key from cache.

        Args:
            key: Cache key to remove.

        Returns:
            True if key was removed, False if it didn't exist.
        """
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Cache invalidated: '{key}'")
            return True
        return False

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove all keys matching a prefix.

        Args:
            prefix: Key prefix to match.

        Returns:
            Number of keys removed.
        """
        keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
        for key in keys_to_remove:
            del self._cache[key]

        if keys_to_remove:
            logger.debug(f"Cache invalidated {len(keys_to_remove)} keys with prefix '{prefix}'")

        return len(keys_to_remove)

    @staticmethod
    def _normalize_symbol(symbol: str | None) -> str:
        """Normalize cache symbol identifiers."""
        normalized = (symbol or "SPX").strip().upper()
        return normalized or "SPX"

    def invalidate_on_spot_move(
        self,
        old_spot: float,
        new_spot: float,
        threshold_pct: float = 0.01,
        *,
        symbol: str | None = None,
        provider: str | None = None,
    ) -> bool:
        """Invalidate GEX-related caches if spot price moves significantly.

        When spot price moves more than threshold (default 1%), the GEX
        calculations become stale because gamma exposure depends on spot.

        Args:
            old_spot: Previous spot price.
            new_spot: Current spot price.
            threshold_pct: Move threshold as decimal (0.01 = 1%).

        Returns:
            True if cache was invalidated, False otherwise.
        """
        if old_spot <= 0:
            return False

        move_pct = abs(new_spot - old_spot) / old_spot

        if move_pct > threshold_pct:
            normalized_symbol = self._normalize_symbol(symbol)
            if provider is not None:
                count = int(self.invalidate(f"gex:current:{normalized_symbol}:{provider}"))
                options_prefix = f"options:chain:{normalized_symbol}:"
                for key in list(self._cache):
                    if key.startswith(options_prefix) and key.endswith(f":{provider}"):
                        count += int(self.invalidate(key))
                legacy_key = f"gex:current:{normalized_symbol}"
                legacy = self.get(legacy_key)
                legacy_provider = (
                    legacy.get("provider") if isinstance(legacy, dict)
                    else getattr(legacy, "provider", None)
                )
                if legacy_provider == provider:
                    count += int(self.invalidate(legacy_key))
            elif symbol is None:
                count = self.invalidate_prefix("gex:")
                count += self.invalidate_prefix("options:")
            else:
                count = 0
                count += int(self.invalidate(f"gex:current:{normalized_symbol}"))
                count += self.invalidate_prefix(f"gex:current:{normalized_symbol}:")
                count += self.invalidate_prefix(f"options:chain:{normalized_symbol}:")

            logger.info(
                f"Spot moved {move_pct:.2%} ({old_spot:.2f} → {new_spot:.2f}) for {normalized_symbol}, "
                f"invalidated {count} cache entries"
            )
            return True

        return False

    def update_spot_price(
        self, spot_price: float, *, symbol: str | None = None, provider: str | None = None
    ) -> bool:
        """Update spot price and check for cache invalidation.

        Args:
            spot_price: Current spot price.
            symbol: Underlying symbol for this spot price. When omitted,
                preserves the legacy global invalidation behavior.

        Returns:
            True if cache was invalidated due to significant move.
        """
        normalized_symbol = self._normalize_symbol(symbol)
        if provider is not None:
            provider = provider.strip().lower()
        baseline_key = f"{normalized_symbol}:{provider}" if provider is not None else normalized_symbol
        invalidated = False

        previous_spot = (
            self._last_spot_prices.get(baseline_key)
            if symbol is not None or provider is not None
            else self._last_spot_price
        )
        if previous_spot is not None:
            invalidated = self.invalidate_on_spot_move(
                previous_spot,
                spot_price,
                symbol=normalized_symbol if symbol is not None else None,
                provider=provider,
            )

        self._last_spot_prices[baseline_key] = spot_price
        self.set(f"spot:price:{baseline_key}", spot_price)

        if provider is None and (symbol is None or normalized_symbol == "SPX"):
            self._last_spot_price = spot_price
            self.set("spot:price", spot_price)

        return invalidated

    def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries cleared.
        """
        count = len(self._cache)
        self._cache.clear()
        self._last_spot_price = None
        self._last_spot_prices.clear()
        logger.info(f"Cache cleared: {count} entries removed")
        return count

    def stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache metrics.
        """
        datetime.now()
        fresh_count = sum(
            1 for key in self._cache if not self.is_stale(key)
        )

        return {
            "total_entries": len(self._cache),
            "fresh_entries": fresh_count,
            "stale_entries": len(self._cache) - fresh_count,
            "last_spot_price": self._last_spot_price,
            "last_spot_prices": dict(self._last_spot_prices),
            "keys": list(self._cache.keys()),
        }


# Global cache instance
_cache_instance: GEXCache | None = None


def get_cache() -> GEXCache:
    """Get or create the global cache instance.

    Returns:
        Global GEXCache instance.
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = GEXCache()
    return _cache_instance


def reset_cache() -> None:
    """Reset the global cache instance (useful for testing)."""
    global _cache_instance
    if _cache_instance is not None:
        _cache_instance.clear()
    _cache_instance = None
