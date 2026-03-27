"""Provider-specific live fetch timeout utilities.

Defines DEFAULT_LIVE_FETCH_TIMEOUT_SECONDS,
TRADIER_LIVE_FETCH_TIMEOUT_SECONDS, and
get_live_fetch_timeout_seconds().
"""

from __future__ import annotations

DEFAULT_LIVE_FETCH_TIMEOUT_SECONDS = 4.0
TRADIER_LIVE_FETCH_TIMEOUT_SECONDS = 45.0


def get_live_fetch_timeout_seconds(provider: str | None) -> float:
    """Return a sane timeout for the requested provider."""
    normalized_provider = (provider or "").strip().lower()
    if normalized_provider == "tradier":
        return TRADIER_LIVE_FETCH_TIMEOUT_SECONDS
    return DEFAULT_LIVE_FETCH_TIMEOUT_SECONDS
