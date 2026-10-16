"""Validation shared by provider-aware HTTP routes."""

from fastapi import HTTPException, Query

from app.core.provider_registry import ProviderRegistry


async def validate_provider_query(provider: str | None = Query(None)) -> None:
    """Reject unknown explicit providers before route fallback/error handling."""
    try:
        ProviderRegistry.resolve_provider_name(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
