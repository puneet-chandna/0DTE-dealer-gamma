"""0DTE GEX Backend - Data Provider Registry.

Centralised factory for retrieving the active data provider instance.
It registers providers and caches instances to avoid repeated connection
overhead.
"""

import logging
from typing import ClassVar, Optional

from app.config import get_settings
from app.core.base_provider import DataProvider
from app.core.tradier_provider import TradierClient
from app.core.yfinance_provider import YFinanceClient

logger = logging.getLogger(__name__)


class ProviderUnavailableError(RuntimeError):
    """Raised when a configured provider cannot be used at runtime."""


class ProviderRegistry:
    """Factory and registry for DataProvider implementations."""

    # Map of name -> Provider Class
    _registry: ClassVar[dict[str, type[DataProvider]]] = {}

    # Map of name -> Cached Provider Instance
    _instances: ClassVar[dict[str, DataProvider]] = {}

    @classmethod
    def register(cls, provider_class: type[DataProvider]) -> None:
        """Register a new provider class."""
        name = provider_class.provider_name
        if not name:
            raise ValueError(f"Provider {provider_class} must set provider_name")
        cls._registry[name] = provider_class
        logger.debug(f"Registered data provider: {name}")

    @staticmethod
    def _normalize_provider_name(name: Optional[str]) -> str:
        """Normalize provider identifiers from config or request input."""
        return (name or "").strip().lower()

    @classmethod
    def resolve_provider_name(
        cls,
        name: Optional[str] = None,
        *,
        default_provider: Optional[str] = None,
    ) -> str:
        """Resolve a provider name against the registry.

        Unknown explicit provider requests are treated as client input
        errors. Unknown configured defaults fall back to ``yfinance`` so
        the app can continue serving traffic.
        """
        configured_default = default_provider
        if configured_default is None:
            configured_default = get_settings().data_provider

        explicit_request = name is not None
        requested_name = cls._normalize_provider_name(
            name if explicit_request else configured_default
        )

        if not requested_name:
            requested_name = "yfinance"

        if requested_name in cls._registry:
            return requested_name

        if explicit_request:
            raise ValueError(f"Unknown provider '{requested_name}'")

        logger.warning(
            f"Provider '{requested_name}' not found. Falling back to 'yfinance'."
        )
        return "yfinance"

    @classmethod
    def get_provider_availability(
        cls,
        name: str,
        provider_cls: Optional[type[DataProvider]] = None,
    ) -> tuple[bool, Optional[str]]:
        """Return runtime availability metadata for a provider."""
        name = cls._normalize_provider_name(name)
        provider_cls = provider_cls or cls._registry.get(name)
        if provider_cls is None:
            return False, f"Unknown provider '{name}'"

        settings = get_settings()

        if name == "tradier" and not settings.tradier_api_key:
            return False, "TRADIER_API_KEY environment variable is missing"

        return True, None

    @classmethod
    def list_providers(cls) -> list[dict]:
        """Return a list of capabilities for all registered providers."""
        caps = []
        for name, provider_cls in cls._registry.items():
            is_available, unavailable_reason = cls.get_provider_availability(
                name, provider_cls
            )
            caps.append(
                {
                    "name": name,
                    "display_name": provider_cls.display_name,
                    "provides_greeks": provider_cls.provides_greeks,
                    "supports_spx_directly": provider_cls.supports_spx_directly,
                    "rate_limit": provider_cls.rate_limit,
                    "requires_api_key": provider_cls.requires_api_key,
                    "is_available": is_available,
                    "unavailable_reason": unavailable_reason,
                    "features": [
                        "spot_price",
                        "options_chain",
                        *(["greeks"] if provider_cls.provides_greeks else []),
                        *(
                            ["spx_direct"]
                            if getattr(provider_cls, "supports_spx_directly", False)
                            else []
                        ),
                    ],
                }
            )
        return caps

    @classmethod
    def get_provider(cls, name: Optional[str] = None) -> DataProvider:
        """Return a configured instance of the named data provider.

        If *name* is omitted, falls back to ``settings.data_provider``.
        Instances are cached per-name to reuse HTTP clients.
        """
        settings = get_settings()
        requested_name = cls.resolve_provider_name(name)

        # Check cache
        if requested_name in cls._instances:
            return cls._instances[requested_name]

        provider_cls = cls._registry[requested_name]
        is_available, unavailable_reason = cls.get_provider_availability(
            requested_name, provider_cls
        )
        if not is_available:
            raise ProviderUnavailableError(
                unavailable_reason
                or f"Provider '{requested_name}' is unavailable"
            )

        # Instantiate based on provider type
        try:
            if requested_name == "tradier":
                instance = provider_cls(
                    api_key=settings.tradier_api_key,
                    base_url=settings.tradier_base_url,
                )
            else:
                # Default for yfinance
                instance = provider_cls()

        except Exception as e:
            logger.error(f"Failed to initialise provider '{requested_name}': {e}")
            raise

        # Cache and return
        cls._instances[requested_name] = instance
        return instance

    @classmethod
    async def close_all(cls) -> None:
        """Close all cached provider instances to release resources."""
        for name, instance in cls._instances.items():
            try:
                await instance.close()
                logger.debug(f"Closed provider: {name}")
            except Exception as e:
                logger.error(f"Error closing provider {name}: {e}")
        cls._instances.clear()


# ---- Auto-registration ----
ProviderRegistry.register(YFinanceClient)
ProviderRegistry.register(TradierClient)


def get_data_client(provider: Optional[str] = None) -> DataProvider:
    """Convenience dependency function for FastAPI routes."""
    return ProviderRegistry.get_provider(provider)
