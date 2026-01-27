"""0DTE GEX Backend - Test Configuration."""

import pytest


@pytest.fixture
def sample_options_data():
    """Sample options chain data for testing."""
    return [
        {
            "strike": 5700.0,
            "type": "call",
            "open_interest": 1000,
            "implied_vol": 0.20,
            "expiration": "2024-10-25",
        },
        {
            "strike": 5700.0,
            "type": "put",
            "open_interest": 800,
            "implied_vol": 0.22,
            "expiration": "2024-10-25",
        },
        {
            "strike": 5750.0,
            "type": "call",
            "open_interest": 1500,
            "implied_vol": 0.18,
            "expiration": "2024-10-25",
        },
    ]


@pytest.fixture
def sample_spot_price():
    """Sample SPX spot price."""
    return 5725.0
