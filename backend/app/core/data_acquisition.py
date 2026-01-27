"""0DTE GEX Backend - Data Acquisition (Placeholder)."""

# TODO: Implement Polygon.io API client
# TODO: Implement CBOE historical data fetcher


class PolygonOptionsCollector:
    """Placeholder for Polygon.io options data collector."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get_options_chain_snapshot(self):
        """Fetch current options chain for SPX 0DTE."""
        raise NotImplementedError("Polygon API integration pending")

    async def get_spot_price(self) -> float:
        """Fetch current SPX spot price."""
        raise NotImplementedError("Polygon API integration pending")
