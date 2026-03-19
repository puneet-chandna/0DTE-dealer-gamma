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

    @classmethod
    def list_providers(cls) -> list[dict]:
        """Return a list of capabilities for all registered providers."""
        caps = []
        for name, provider_cls in cls._registry.items():
            # Create a dummy instance just to read the class-level metadata properly,
            # or rely on the class attributes directly.
            caps.append(
                {
                    "name": name,
                    "display_name": provider_cls.display_name,
                    "provides_greeks": provider_cls.provides_greeks,
                    "supports_spx_directly": provider_cls.supports_spx_directly,
                    "rate_limit": provider_cls.rate_limit,
                    "requires_api_key": provider_cls.requires_api_key,
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
        requested_name = name or settings.data_provider

        # Check cache
        if requested_name in cls._instances:
            return cls._instances[requested_name]

        # Ensure registered
        if requested_name not in cls._registry:
            # Fallback to yfinance if the requested provider is missing
            logger.warning(
                f"Provider '{requested_name}' not found. "
                "Falling back to 'yfinance'."
            )
            requested_name = "yfinance"

        provider_cls = cls._registry[requested_name]

        # Instantiate based on provider type
        try:
            if requested_name == "tradier":
                settings = get_settings()
                if not settings.tradier_api_key:
                    raise ValueError(
                        "TRADIER_API_KEY environment variable is missing"
                    )

                instance = provider_cls(
                    api_key=settings.tradier_api_key,
                    base_url=settings.tradier_base_url,
                )
            else:
                # Default for yfinance
                instance = provider_cls()

        except Exception as e:
            logger.error(f"Failed to initialise provider '{requested_name}': {e}")
            if requested_name != "yfinance":
                logger.warning("Falling back to yfinance")
                instance = YFinanceClient()
            else:
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
