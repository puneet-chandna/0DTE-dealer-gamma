"""0DTE GEX Backend - Abstract Data Provider Interface.

Defines the contract all data providers must implement.
Each provider fetches spot prices, option expirations, and options chains
in a standardised DataFrame format that feeds the GEX calculator.
"""

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class DataProvider(ABC):
    """Base class for all market-data providers.

    Subclasses MUST set the class-level metadata attributes and implement
    every abstract method listed below.

    Class Attributes:
        provider_name:         Short slug, e.g. ``"yfinance"`` or ``"tradier"``.
        display_name:          Human-friendly name for UI display.
        provides_greeks:       ``True`` when the provider returns Greeks directly.
        supports_spx_directly: ``True`` when SPX options are available (not via SPY proxy).
        rate_limit:            Maximum requests per minute.
        requires_api_key:      ``True`` when an API key is needed.
    """

    # ---- Metadata (override in every subclass) ----
    provider_name: str = ""
    display_name: str = ""
    provides_greeks: bool = False
    supports_spx_directly: bool = False
    rate_limit: int = 5
    requires_api_key: bool = False

    # ------------------------------------------------------------------ #
    #  Required interface                                                  #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def get_spot_price(self, symbol: str = "SPX") -> float:
        """Return the current spot price for *symbol*.

        Raises:
            ValueError: If the price cannot be fetched.
        """

    @abstractmethod
    async def get_expirations(self, underlying: str = "SPX") -> list[str]:
        """Return available expiration dates as ``YYYY-MM-DD`` strings."""

    @abstractmethod
    async def get_options_chain_snapshot(
        self,
        underlying: str = "SPX",
        expiration_date: date | None = None,
    ) -> pd.DataFrame:
        """Fetch the options chain for a given underlying and expiration.

        The returned DataFrame **must** contain at least these columns::

            symbol, strike, expiration, type,
            bid, ask, mid, open_interest, volume,
            implied_vol, delta, gamma, vega, theta

        ``delta``–``theta`` may be ``None`` if the provider does not
        supply Greeks (see *provides_greeks*).
        """

    @abstractmethod
    async def get_options_chain_for_gex(
        self,
        underlying: str = "SPX",
    ) -> tuple[pd.DataFrame, float]:
        """Return a *filtered* options chain ready for GEX calculation.

        Applies 0DTE + strike-range filters and returns
        ``(options_df, spot_price)``.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release resources held by the provider (HTTP clients, etc.)."""

    # ------------------------------------------------------------------ #
    #  Shared helpers                                                      #
    # ------------------------------------------------------------------ #

    def get_capabilities(self) -> dict:
        """Return a JSON-safe summary of this provider's features.

        Used by the frontend to adapt the UI per provider.
        """
        features = ["spot_price", "options_chain"]
        if self.provides_greeks:
            features.append("greeks")
        if self.supports_spx_directly:
            features.append("spx_direct")

        return {
            "name": self.provider_name,
            "display_name": self.display_name,
            "provides_greeks": self.provides_greeks,
            "supports_spx_directly": self.supports_spx_directly,
            "rate_limit": self.rate_limit,
            "requires_api_key": self.requires_api_key,
            "features": features,
        }
