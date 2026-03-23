"""Tests for provider registry behavior."""

from unittest.mock import patch

import pytest

from app.core.provider_registry import ProviderRegistry


@pytest.fixture(autouse=True)
def reset_provider_registry_instances():
    """Keep provider registry instance cache isolated between tests."""
    ProviderRegistry._instances.clear()
    yield
    ProviderRegistry._instances.clear()


def test_list_providers_includes_runtime_availability_metadata():
    """Provider metadata should expose availability for UI gating."""
    providers = ProviderRegistry.list_providers()

    assert providers
    provider_names = {provider["name"] for provider in providers}
    assert {"yfinance", "tradier"}.issubset(provider_names)

    for provider in providers:
        assert "is_available" in provider
        assert "unavailable_reason" in provider


def test_tradier_reports_unavailable_without_api_key():
    """Tradier should be marked unavailable when the API key is missing."""
    with patch("app.core.provider_registry.get_settings") as mock_get_settings:
        mock_get_settings.return_value.data_provider = "yfinance"
        mock_get_settings.return_value.tradier_api_key = None
        mock_get_settings.return_value.tradier_base_url = "https://api.tradier.com/v1"

        providers = ProviderRegistry.list_providers()

    tradier = next(provider for provider in providers if provider["name"] == "tradier")
    assert tradier["is_available"] is False
    assert tradier["unavailable_reason"]
