"""0DTE GEX Backend - GEX API Endpoints.

Provides real-time GEX data, strike breakdowns, and market regime detection.
"""

import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.core import (
    GEXCalculator,
    ProviderRegistry,
    get_data_client,
)
from app.core.advanced_analytics import enrich_snapshot_with_advanced_analytics
from app.core.demo_data import get_demo_data_service
from app.core.provider_timeouts import get_live_fetch_timeout_seconds
from app.core.rate_provider import get_rate_provider
from app.core.snapshot_quality import annotate_snapshot_quality, is_snapshot_replay_eligible
from app.models.schemas import (
    GEXByStrike,
    GEXHistorical,
    GEXSnapshot,
    RegimeData,
)
from app.services.cache import get_cache
from app.services.historical_data import get_historical_data_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Eastern Time timezone
ET = ZoneInfo("America/New_York")
# Module-level instances (lazy initialization)
_gex_calculator: GEXCalculator | None = None


def get_gex_calculator() -> GEXCalculator:
    """Get or create the GEX calculator instance."""
    global _gex_calculator
    if _gex_calculator is None:
        _gex_calculator = GEXCalculator(rate_provider=get_rate_provider())
    return _gex_calculator


async def _get_live_gex_snapshot(
    symbol: str,
    provider: str | None = None
) -> dict:
    """Fetch live data and calculate GEX snapshot.

    Args:
        symbol: The underlying symbol (e.g. "SPX").
        provider: Optional data provider name (e.g. "yfinance", "tradier").
    """
    gex_calculator = get_gex_calculator()
    data_client = get_data_client(provider)

    # Log appropriate message
    request_symbol = getattr(data_client, "_get_ticker_symbol", lambda s: s)(symbol)
    logger.info(f"Fetching live options data for {symbol} ({request_symbol}) via {data_client.provider_name}")

    # Fetch filtered data
    options_df, spot_price = await data_client.get_options_chain_for_gex(
        underlying=symbol
    )

    if options_df.empty:
        logger.warning(f"No valid 0DTE options data found for {symbol} (possibly weekend). Falling back to mock data.")
        mock_snapshot = _generate_mock_gex_snapshot(spot_price=spot_price)
        raw = mock_snapshot.model_dump()
        raw["provider"] = f"mock ({data_client.provider_name} empty)"
        return raw

    # Calculate live GEX
    snapshot = gex_calculator.calculate_gex_from_chain(
        options_df=options_df,
        spot_price=spot_price,
        timestamp=datetime.now(ET),
    )
    snapshot = annotate_snapshot_quality(
        snapshot,
        options_df=options_df,
        provider=data_client.provider_name,
    )
    snapshot = enrich_snapshot_with_advanced_analytics(
        snapshot,
        options_df=options_df,
        symbol=symbol,
        provider=data_client.provider_name,
    )

    # Add provider info
    raw = snapshot.model_dump()
    raw["provider"] = data_client.provider_name
    return raw


async def _get_replay_snapshot(
    symbol: str,
    provider: str,
) -> GEXSnapshot | None:
    """Return the latest stored snapshot for replay/demo mode when available."""
    today_et = datetime.now(ET).date()
    snapshots = await get_historical_data_service().get_historical_snapshots(
        provider=provider,
        symbol=symbol,
        start_date=today_et,
        end_date=today_et,
        interval="5s",
        prefer_replay=True,
    )
    if not snapshots:
        return None
    return snapshots[-1]


async def _get_latest_persisted_snapshot(
    *,
    symbol: str,
    provider: str,
    prefer_replay: bool = False,
) -> GEXSnapshot | None:
    """Return the latest persisted snapshot when the live path is unavailable."""
    return await get_historical_data_service().get_latest_snapshot(
        provider=provider,
        symbol=symbol,
        prefer_replay=prefer_replay,
        replay_eligible_only=True,
    )


async def _get_demo_anchor_snapshot(
    *,
    symbol: str,
    provider: str,
) -> GEXSnapshot | None:
    """Return the latest persisted snapshot to shape synthetic demo data."""
    return await _get_latest_persisted_snapshot(
        symbol=symbol,
        provider=provider,
        prefer_replay=False,
    )


def _serialize_persisted_snapshot(snapshot: GEXSnapshot, *, provider: str) -> dict:
    """Mark persisted fallback payloads so the frontend can distinguish them."""
    payload = snapshot.model_dump()
    payload["provider"] = provider
    payload.setdefault("metrics", {})
    payload["metrics"]["is_persisted_fallback"] = 1.0
    return payload


def _snapshot_is_mock(snapshot_payload: dict) -> bool:
    """Detect generated fallback snapshots masquerading as live data."""
    metrics = snapshot_payload.get("metrics") or {}
    provider = str(snapshot_payload.get("provider", "")).lower()
    return bool(metrics.get("is_mock_data") == 1.0 or provider.startswith("mock"))


def _coerce_snapshot_payload(snapshot_like, *, provider: str | None = None) -> dict:
    if hasattr(snapshot_like, "model_dump"):
        payload = snapshot_like.model_dump()
    else:
        payload = dict(snapshot_like)
    if provider is not None:
        payload["provider"] = payload.get("provider", provider)
    return payload


def _get_cached_snapshot_payload(
    *,
    cache,
    cache_key: str,
    legacy_key: str | None,
    provider: str,
    fresh_only: bool,
) -> dict | None:
    getter = cache.get_if_fresh if fresh_only else cache.get
    freshness_label = "fresh" if fresh_only else "stale"

    for key in (cache_key, legacy_key):
        if key is None:
            continue

        cached_snapshot = getter(key)
        if cached_snapshot is None:
            continue

        payload = _coerce_snapshot_payload(cached_snapshot, provider=provider)
        if is_snapshot_replay_eligible(payload):
            return payload

        logger.warning(
            "Ignoring low-quality %s cached snapshot for %s (%s)",
            freshness_label,
            key,
            provider,
        )

    return None


async def _resolve_best_snapshot_payload(
    *,
    symbol: str,
    active_provider: str,
    default_provider: str,
    cache,
) -> dict:
    cache_key = f"gex:current:{symbol}:{active_provider}"
    legacy_key = (
        f"gex:current:{symbol}"
        if active_provider == default_provider
        else None
    )

    fresh_snapshot = _get_cached_snapshot_payload(
        cache=cache,
        cache_key=cache_key,
        legacy_key=legacy_key,
        provider=active_provider,
        fresh_only=True,
    )
    if fresh_snapshot is not None:
        logger.debug("Serving current GEX from cache for %s (%s)", symbol, active_provider)
        return fresh_snapshot

    live_error: Exception | None = None
    try:
        live_snapshot = await asyncio.wait_for(
            _get_live_gex_snapshot(symbol, active_provider),
            timeout=get_live_fetch_timeout_seconds(active_provider),
        )

        if _snapshot_is_mock(live_snapshot):
            live_error = RuntimeError("live provider returned mock data")
        elif not is_snapshot_replay_eligible(live_snapshot):
            live_error = RuntimeError("live provider returned a low-quality snapshot")
        else:
            cache.set(cache_key, live_snapshot)
            if legacy_key is not None:
                cache.set(legacy_key, live_snapshot)
            return live_snapshot
    except Exception as exc:
        live_error = exc

    stale_snapshot = _get_cached_snapshot_payload(
        cache=cache,
        cache_key=cache_key,
        legacy_key=legacy_key,
        provider=active_provider,
        fresh_only=False,
    )
    if stale_snapshot is not None:
        logger.warning("Returning stale cached GEX snapshot for %s (%s)", symbol, active_provider)
        return stale_snapshot

    persisted_snapshot = await _get_latest_persisted_snapshot(
        symbol=symbol,
        provider=active_provider,
    )
    if persisted_snapshot is not None:
        logger.warning(
            "Returning latest persisted GEX snapshot for %s (%s)",
            symbol,
            active_provider,
        )
        return _serialize_persisted_snapshot(
            persisted_snapshot,
            provider=active_provider,
        )

    if live_error is not None:
        raise live_error

    raise RuntimeError("No usable snapshot is available")


def _generate_mock_gex_snapshot(spot_price: float = 5950.0) -> GEXSnapshot:
    """Generate a mock GEX snapshot for demo/testing purposes."""
    import numpy as np

    now = datetime.now(ET)

    # Generate realistic mock data
    np.random.seed(int(now.timestamp()) % 10000)
    net_gex = np.random.uniform(-3e9, 2e9)
    call_gex = np.random.uniform(-2e9, -0.5e9)
    put_gex = net_gex - call_gex

    # Generate strike breakdown
    strikes = np.arange(spot_price - 100, spot_price + 105, 5)
    gex_by_strike = {}
    for strike in strikes:
        distance = abs(strike - spot_price)
        magnitude = np.exp(-distance / 50) * np.random.uniform(-5e8, 5e8)
        gex_by_strike[float(strike)] = float(magnitude)

    # Find dominant strike
    dominant_strike = max(gex_by_strike.keys(), key=lambda k: abs(gex_by_strike[k]))

    # Zero gamma level (mock)
    zgl = spot_price + np.random.uniform(-20, 20)

    return GEXSnapshot(
        timestamp=now,
        spot_price=spot_price,
        total_call_gex=call_gex,
        total_put_gex=put_gex,
        net_gex=net_gex,
        zero_gamma_level=zgl,
        gex_by_strike=gex_by_strike,
        dominant_strike=dominant_strike,
        metrics={
            "regime_code": 0.0 if net_gex > 0 else -1.0,
            "gex_imbalance": abs(call_gex) / max(abs(put_gex), 1),
            "is_mock_data": 1.0,
            "capture_quality": 0.0,
            "quality_flags": ["mock_data"],
            "meaningful_strike_count": float(len(gex_by_strike)),
            "is_replay_eligible": False,
        },
    )


@router.get("/current", response_model=GEXSnapshot)
async def get_current_gex(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    provider: str | None = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    demo: bool = Query(False, description="Return deterministic demo data"),
):
    """
    Get the most recent 0DTE GEX calculation.
    """
    settings = get_settings()
    active_provider = ProviderRegistry.resolve_provider_name(
        provider,
        default_provider=settings.data_provider,
    )

    if demo:
        replay_snapshot = await _get_replay_snapshot(symbol=symbol, provider=active_provider)
        if replay_snapshot is not None:
            replay_snapshot = get_demo_data_service().ensure_snapshot_advanced_analytics(
                snapshot=replay_snapshot.model_copy(deep=True),
                symbol=symbol,
                provider=active_provider,
            )
            replay_payload = replay_snapshot.model_dump()
            replay_payload["provider"] = active_provider
            replay_payload.setdefault("metrics", {})
            replay_payload["metrics"]["is_replay_data"] = 1.0
            return replay_payload
        anchor_snapshot = await _get_demo_anchor_snapshot(
            symbol=symbol,
            provider=active_provider,
        )
        demo_snapshot = get_demo_data_service().get_current_snapshot(
            symbol=symbol,
            anchor_snapshot=anchor_snapshot,
            provider=active_provider,
        )
        replay_payload = demo_snapshot.model_dump()
        replay_payload["provider"] = active_provider
        return replay_payload

    default_provider = ProviderRegistry.resolve_provider_name(
        default_provider=settings.data_provider,
    )

    cache = get_cache()
    try:
        snapshot_dict = await _resolve_best_snapshot_payload(
            symbol=symbol,
            active_provider=active_provider,
            default_provider=default_provider,
            cache=cache,
        )
        return snapshot_dict
    except Exception as e:
        logger.error(f"Failed to compute live GEX: {e}")
        raise HTTPException(status_code=503, detail=f"Unable to fetch GEX data: {str(e)}")


@router.get("/historical", response_model=GEXHistorical)
async def get_historical_gex(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    provider: str | None = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    interval: str = Query("1h", description="Data interval: 5s, 1m, 5m, 15m, 1h, 1d, 1wk"),
    demo: bool = Query(False, description="Return deterministic demo data"),
) -> GEXHistorical:
    """Get historical GEX data for date range.

    Note: Currently returns synthetic data for demonstration.
    """
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")
    if (end_date - start_date).days > 365:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 365 days")

    try:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        settings = get_settings()
        active_provider = ProviderRegistry.resolve_provider_name(
            provider,
            default_provider=settings.data_provider,
        )

        persisted_snapshots = await get_historical_data_service().get_historical_snapshots(
            provider=active_provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            prefer_replay=demo,
        )
        if persisted_snapshots:
            return GEXHistorical(
                data=persisted_snapshots,
                start_date=start_dt,
                end_date=end_dt,
                count=len(persisted_snapshots),
            )

        if demo:
            anchor_snapshot = await _get_demo_anchor_snapshot(
                symbol=symbol,
                provider=active_provider,
            )
            snapshots = get_demo_data_service().get_historical_snapshots(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                interval=interval,
                anchor_snapshot=anchor_snapshot,
            )
            return GEXHistorical(
                data=snapshots[:100],
                start_date=start_dt,
                end_date=end_dt,
                count=len(snapshots[:100]),
            )

        return GEXHistorical(
            data=[],
            start_date=start_dt,
            end_date=end_dt,
            count=0,
        )

    except Exception as e:
        logger.error(f"Failed to generate historical GEX data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate historical data: {str(e)}")


@router.get("/strikes", response_model=GEXByStrike)
async def get_gex_by_strikes(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    provider: str | None = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    demo: bool = Query(False, description="Return deterministic demo data"),
):
    """Get GEX values separated by strike price."""
    if demo:
        settings = get_settings()
        active_provider = ProviderRegistry.resolve_provider_name(
            provider,
            default_provider=settings.data_provider,
        )
        snapshot = await _get_replay_snapshot(symbol=symbol, provider=active_provider)
        if snapshot is None:
            anchor_snapshot = await _get_demo_anchor_snapshot(
                symbol=symbol,
                provider=active_provider,
            )
            snapshot = get_demo_data_service().get_current_snapshot(
                symbol=symbol,
                anchor_snapshot=anchor_snapshot,
                provider=active_provider,
            )
        sorted_strikes = sorted(snapshot.gex_by_strike.keys())
        sorted_values = [snapshot.gex_by_strike[strike] for strike in sorted_strikes]
        return GEXByStrike(
            strikes=sorted_strikes,
            gex_values=sorted_values,
            spot_price=snapshot.spot_price,
            zero_gamma_level=snapshot.zero_gamma_level,
        )

    cache = get_cache()
    settings = get_settings()
    active_provider = ProviderRegistry.resolve_provider_name(
        provider,
        default_provider=settings.data_provider,
    )
    default_provider = ProviderRegistry.resolve_provider_name(
        default_provider=settings.data_provider,
    )
    try:
        snapshot_dict = await _resolve_best_snapshot_payload(
            symbol=symbol,
            active_provider=active_provider,
            default_provider=default_provider,
            cache=cache,
        )
        snapshot = GEXSnapshot(**snapshot_dict)
        gex_by_strike = snapshot.gex_by_strike
        sorted_strikes = sorted(gex_by_strike.keys())
        sorted_values = [gex_by_strike[s] for s in sorted_strikes]

        return GEXByStrike(
            strikes=sorted_strikes,
            gex_values=sorted_values,
            spot_price=snapshot.spot_price,
            zero_gamma_level=snapshot.zero_gamma_level,
        )
    except Exception as e:
        logger.error(f"Failed to get GEX by strikes for {symbol}: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to get GEX by strikes: {e}")


@router.get("/regime", response_model=RegimeData)
async def get_market_regime(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    provider: str | None = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    demo: bool = Query(False, description="Return deterministic demo data"),
):
    """Get current market regime based on GEX positioning."""
    if demo:
        settings = get_settings()
        active_provider = ProviderRegistry.resolve_provider_name(
            provider,
            default_provider=settings.data_provider,
        )
        snapshot = await _get_replay_snapshot(symbol=symbol, provider=active_provider)
        if snapshot is None:
            anchor_snapshot = await _get_demo_anchor_snapshot(
                symbol=symbol,
                provider=active_provider,
            )
            snapshot = get_demo_data_service().get_current_snapshot(
                symbol=symbol,
                anchor_snapshot=anchor_snapshot,
                provider=active_provider,
            )
        regime, description, color = get_gex_calculator().determine_regime(snapshot.net_gex)
        return RegimeData(
            regime=regime,
            description=description,
            color=color,
            net_gex=snapshot.net_gex,
            net_gex_billions=snapshot.net_gex / 1e9,
            timestamp=snapshot.timestamp,
        )

    cache = get_cache()

    settings = get_settings()
    active_provider = ProviderRegistry.resolve_provider_name(
        provider,
        default_provider=settings.data_provider,
    )
    default_provider = ProviderRegistry.resolve_provider_name(
        default_provider=settings.data_provider,
    )
    try:
        snapshot_dict = await _resolve_best_snapshot_payload(
            symbol=symbol,
            active_provider=active_provider,
            default_provider=default_provider,
            cache=cache,
        )
        snapshot = GEXSnapshot(**snapshot_dict)

        gex_calculator = get_gex_calculator()
        regime, description, color = gex_calculator.determine_regime(snapshot.net_gex)

        return RegimeData(
            regime=regime,
            description=description,
            color=color,
            net_gex=snapshot.net_gex,
            net_gex_billions=snapshot.net_gex / 1e9,
            timestamp=snapshot.timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to get regime for {symbol}: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to determine regime: {e}")
