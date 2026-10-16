"""0DTE GEX Backend - Analytics API Endpoints.

Provides GEX-volatility analysis, backtesting, and summary statistics.
"""

import asyncio
import logging
from dataclasses import asdict
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import validate_provider_query
from app.config import get_settings
from app.core import (
    ProviderRegistry,
    TradingStrategy,
    VolatilityAnalyzer,
    get_current_trading_date,
    get_data_client,
)
from app.core.demo_data import get_demo_data_service
from app.core.provenance import data_provenance
from app.core.provider_registry import ProviderUnavailableError
from app.models.schemas import (
    AnalyticsResult,
    BacktestResult,
    IVSurfaceResponse,
    SummaryStatistics,
    VectorBTBacktestResult,
)
from app.services.cache import get_cache
from app.services.historical_data import get_historical_data_service

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(validate_provider_query)])

# Eastern Time timezone
ET = ZoneInfo("America/New_York")


def _technical_indicator_payload_has_values(payload: dict | None) -> bool:
    """Return True when at least one requested indicator has a usable numeric value."""
    if payload is None:
        return False

    for point in payload.get("data", []):
        if any(
            point.get(field) is not None
            for field in ("atr", "rsi", "bb_upper", "bb_mid", "bb_lower")
        ):
            return True

    return False


def _build_technical_indicator_response(
    *,
    symbol: str,
    period: str,
    indicator_list: list[str],
    result_df: pd.DataFrame,
) -> dict:
    """Serialize computed technical indicators into the API response shape."""
    data = []
    for idx, row in result_df.iterrows():
        point = {
            "timestamp": str(idx),
            "close": float(row["close"]),
        }
        if "atr" in result_df.columns:
            val = row["atr"]
            point["atr"] = None if pd.isna(val) else float(val)
        if "rsi" in result_df.columns:
            val = row["rsi"]
            point["rsi"] = None if pd.isna(val) else float(val)
        for bb_key in ("bb_upper", "bb_mid", "bb_lower"):
            if bb_key in result_df.columns:
                val = row[bb_key]
                point[bb_key] = None if pd.isna(val) else float(val)
        data.append(point)

    return {
        "symbol": symbol,
        "period": period,
        "indicators": indicator_list,
        "data": data,
        "count": len(data),
    }


def _load_yfinance_history(
    *,
    symbol: str,
    period: str,
    interval: str,
) -> pd.DataFrame:
    """Fetch historical price data from Yahoo Finance for indicator computation."""
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    return ticker.history(period=period, interval=interval)


async def _get_demo_backtest_series(
    *,
    provider: str,
    symbol: str,
    start_date: date,
    end_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return requested-range demo data anchored to the latest same-provider snapshot."""
    anchor_snapshot = await get_historical_data_service().get_latest_snapshot(
        provider=provider,
        symbol=symbol,
    )
    return get_demo_data_service().get_time_series(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        anchor_snapshot=anchor_snapshot,
    )


def _reject_future_backtest_dates(start_date: date, end_date: date) -> None:
    """Reject requested backtests that extend past the current New York market date."""
    market_date = get_current_trading_date()
    if start_date > market_date or end_date > market_date:
        raise HTTPException(
            status_code=400,
            detail=(
                "Backtest dates cannot be after the current New York market date "
                f"({market_date.isoformat()})."
            ),
        )


async def _analytics_frames(
    *, provider: str, symbol: str, start_date: date, end_date: date, demo: bool
):
    if demo:
        return await _get_demo_backtest_series(
            provider=provider, symbol=symbol, start_date=start_date, end_date=end_date
        )
    frames = await get_historical_data_service().get_time_series_frames(
        provider=provider,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        interval="1m",
        prefer_replay=True,
        allow_latest_replay_fallback=False,
    )
    if len(frames[0]) < 2 or len(frames[1]) < 2:
        raise HTTPException(
            status_code=404,
            detail="Insufficient quality-eligible captured history for the requested provider, symbol and dates. Capture sessions first or explicitly enable demo mode.",
        )
    return frames


def _backtest_instrument(provider: str, symbol: str, demo: bool) -> None:
    if symbol.upper() == "SPX" and provider != "yfinance" and not demo:
        raise HTTPException(
            status_code=422,
            detail="SPX is an index, not a tradable stock. Use captured SPY history for a long-underlying simulation.",
        )


def _backtest_prices(prices: pd.DataFrame, *, provider: str, symbol: str) -> pd.DataFrame:
    if provider == "yfinance" and symbol.upper() == "SPX":
        prices = prices.copy()
        columns = prices.columns.intersection(["open", "high", "low", "close"])
        prices[columns] = prices[columns] / 10.0
    return prices


def _validate_analytics_dates(start_date: date, end_date: date) -> None:
    if start_date > end_date or (end_date - start_date).days > 365:
        raise HTTPException(
            status_code=400, detail="Choose an ordered date range of at most 365 days."
        )
    _reject_future_backtest_dates(start_date, end_date)


@router.get("/gex-volatility", response_model=AnalyticsResult)
async def analyze_gex_volatility(
    start_date: date = Query(...),
    end_date: date = Query(...),
    symbol: str = Query("SPX"),
    provider: str | None = Query(None),
    demo: bool = Query(False),
) -> AnalyticsResult:
    """Descriptive GEX/volatility association; predictive evidence requires the held-out study."""
    _validate_analytics_dates(start_date, end_date)
    try:
        active_provider = ProviderRegistry.resolve_provider_name(provider)
        prices, gex = await _analytics_frames(
            provider=active_provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            demo=demo,
        )
        result = VolatilityAnalyzer.analyze_gex_volatility_relationship(gex, prices)
        provenance = data_provenance(gex, provider=active_provider, symbol=symbol, synthetic=demo)
        provenance.quality_limitations.append(
            "Descriptive association with overlapping volatility windows; the nominal Welch p-value is not dependence-corrected and is not predictive evidence."
        )
        return result.model_copy(update={"provenance": provenance})
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/backtest", response_model=BacktestResult)
async def backtest_strategy(
    symbol: str = Query("SPX"),
    provider: str | None = Query(None),
    strategy: str = Query(
        "gex_long_underlying",
        description="Directional long underlying; volatility_breakout is a deprecated name",
    ),
    start_date: date = Query(...),
    end_date: date = Query(...),
    entry_threshold: float = Query(-1e9, allow_inf_nan=False),
    exit_threshold: float = Query(0.0, allow_inf_nan=False),
    stop_loss_pct: float = Query(0.02, gt=0, le=0.5, allow_inf_nan=False),
    take_profit_pct: float = Query(0.05, gt=0, le=1.0, allow_inf_nan=False),
    initial_cash: float = Query(100_000.0, gt=0, allow_inf_nan=False),
    fees: float = Query(0.001, ge=0, lt=1, allow_inf_nan=False),
    slippage: float = Query(0.001, ge=0, lt=1, allow_inf_nan=False),
    position_size: float = Query(1.0, gt=0, le=1, allow_inf_nan=False),
    execution_delay_bars: int = Query(1, ge=1, le=30),
    demo: bool = Query(False),
) -> BacktestResult:
    """Directional equity simulation with close-observed stops; no long-volatility claim."""
    _validate_analytics_dates(start_date, end_date)
    if (
        strategy not in {"gex_long_underlying", "volatility_breakout"}
        or entry_threshold >= exit_threshold
    ):
        raise HTTPException(
            status_code=400,
            detail="Use gex_long_underlying with entry_threshold below exit_threshold.",
        )
    try:
        active_provider = ProviderRegistry.resolve_provider_name(provider)
        _backtest_instrument(active_provider, symbol, demo)
        prices, gex = await _analytics_frames(
            provider=active_provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            demo=demo,
        )
        result = TradingStrategy.volatility_breakout_strategy(
            gex_data=gex,
            price_data=_backtest_prices(prices, provider=active_provider, symbol=symbol),
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            initial_cash=initial_cash,
            fees=fees,
            slippage=slippage,
            position_size=position_size,
            execution_delay_bars=execution_delay_bars,
        )
        payload = asdict(result)
        provenance = data_provenance(gex, provider=active_provider, symbol=symbol, synthetic=demo)
        provenance.quality_limitations.append(
            "Long-underlying simulation: sampled close fills, assumed fees/slippage, delayed close-observed stops and overnight positions; no verified executable quote or market-impact model."
        )
        payload.update(strategy="gex_long_underlying", provenance=provenance)
        return BacktestResult(**payload)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/summary-statistics", response_model=SummaryStatistics)
async def get_summary_stats(
    symbol: str = Query("SPX"),
    provider: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    demo: bool = Query(False),
) -> SummaryStatistics:
    end_date = end_date or get_current_trading_date()
    start_date = start_date or end_date.replace(day=1)
    _validate_analytics_dates(start_date, end_date)
    try:
        active_provider = ProviderRegistry.resolve_provider_name(provider)
        _, gex = await _analytics_frames(
            provider=active_provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            demo=demo,
        )
        result = VolatilityAnalyzer.compute_summary_statistics(gex)
        return result.model_copy(
            update={
                "provenance": data_provenance(
                    gex, provider=active_provider, symbol=symbol, synthetic=demo
                )
            }
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ============================================================================
# New Integration Endpoints
# ============================================================================


@router.get("/iv-surface", response_model=IVSurfaceResponse)
async def get_iv_surface(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    provider: str | None = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    demo: bool = Query(False, description="Return deterministic demo data"),
) -> IVSurfaceResponse:
    """Get Implied Volatility Surface data for 3D charting.

    Creates a mock surface or true surface based on available options data.
    """
    from app.core.rate_provider import get_rate_provider
    from app.core.vollib_bridge import VolLibBridge

    try:
        settings = get_settings()
        active_provider = ProviderRegistry.resolve_provider_name(
            provider,
            default_provider=settings.data_provider,
        )

        persisted_surface = await get_historical_data_service().get_iv_surface(
            provider=active_provider,
            symbol=symbol,
            prefer_replay=demo,
        )
        if persisted_surface is not None:
            return persisted_surface

        if demo:
            anchor_snapshot = await get_historical_data_service().get_latest_snapshot(
                provider=active_provider,
                symbol=symbol,
            )
            return get_demo_data_service().get_iv_surface(
                symbol=symbol,
                anchor_snapshot=anchor_snapshot,
            )

        data_client = get_data_client(active_provider)

        # In a real scenario, we'd fetch multiple expirations.
        # For now, we'll fetch the nearest chain and generate a realistic surface from it.
        try:
            options_df, spot_price = await get_cache().fetch_gex_chain(data_client, symbol)
        except Exception as e:
            logger.warning(
                f"Could not fetch live options for IV surface via {data_client.provider_name}: {e}"
            )
            options_df = pd.DataFrame()
            spot_price = 5950.0  # Fallback

        # Get live rate
        rate = get_rate_provider().get_rate()

        if options_df.empty:
            return {
                "symbol": symbol,
                "spot_price": spot_price,
                "surface": [],
                "skew": [],
                "count": 0,
            }

        # Add time-to-expiry column if not present
        if "T" not in options_df.columns:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            now = datetime.now(ZoneInfo("America/New_York"))
            expiration = pd.to_datetime(options_df["expiration"])
            options_df["T"] = (expiration - now).dt.total_seconds() / (365.25 * 24 * 3600)
            options_df["T"] = options_df["T"].clip(lower=1e-10)

        # Calculate mid price if not present
        if "mid" not in options_df.columns and "bid" in options_df.columns:
            options_df["mid"] = (options_df["bid"] + options_df["ask"]) / 2

        # Compute IV surface
        surface_df = VolLibBridge.calculate_iv_surface(options_df, spot_price, r=rate)

        if surface_df.empty:
            return {
                "symbol": symbol,
                "spot_price": spot_price,
                "surface": [],
                "skew": [],
                "count": 0,
            }

        # Compute skew
        skew_df = VolLibBridge.calculate_iv_skew(surface_df)

        return {
            "symbol": symbol,
            "spot_price": spot_price,
            "surface": surface_df.to_dict(orient="records"),
            "skew": skew_df.to_dict(orient="records") if not skew_df.empty else [],
            "count": len(surface_df),
        }

    except HTTPException:
        raise
    except ProviderUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"IV surface computation failed: {e}")
        raise HTTPException(status_code=500, detail=f"IV surface failed: {str(e)}")


@router.get("/technical-indicators")
async def get_technical_indicators(
    symbol: str = Query("SPY", description="Symbol to analyze"),
    provider: str | None = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    period: str = Query("1mo", description="Data period (1d, 5d, 1mo, 3mo, 6mo, 1y)"),
    interval: str = Query("1d", description="Data interval (1m, 5m, 15m, 1h, 1d)"),
    indicators: str = Query("ATR,RSI,BBANDS", description="Comma-separated indicators"),
    demo: bool = Query(False, description="Return deterministic demo data"),
) -> dict:
    """Get technical indicators for a symbol using pandas-ta.

    Supports: ATR (Average True Range), RSI (Relative Strength Index),
    BBANDS (Bollinger Bands).

    Feature idea: overlay with GEX levels to detect volatility explosions.
    """
    from app.core.technical_indicators import TechnicalIndicatorEngine

    try:
        settings = get_settings()
        active_provider = ProviderRegistry.resolve_provider_name(
            provider,
            default_provider=settings.data_provider,
        )
        indicator_list = [item.strip().upper() for item in indicators.split(",")]

        persisted_indicators = await get_historical_data_service().get_technical_indicators(
            provider=active_provider,
            symbol=symbol,
            period=period,
            interval=interval,
            indicators=indicator_list,
            prefer_replay=demo,
        )
        if persisted_indicators is not None and (
            not demo or _technical_indicator_payload_has_values(persisted_indicators)
        ):
            return persisted_indicators

        if demo:
            try:
                hist = await asyncio.to_thread(
                    _load_yfinance_history,
                    symbol=symbol,
                    period=period,
                    interval=interval,
                )
            except Exception as exc:
                logger.warning(
                    "Demo technical indicators fell back from yfinance history for %s: %s",
                    symbol,
                    exc,
                )
                hist = pd.DataFrame()

            if not hist.empty:
                result_df = await asyncio.to_thread(
                    TechnicalIndicatorEngine.compute_indicators,
                    hist,
                    indicators=indicator_list,
                )
                response = await asyncio.to_thread(
                    _build_technical_indicator_response,
                    symbol=symbol,
                    period=period,
                    indicator_list=indicator_list,
                    result_df=result_df,
                )
                if _technical_indicator_payload_has_values(response):
                    return response

            anchor_snapshot = await get_historical_data_service().get_latest_snapshot(
                provider=active_provider,
                symbol=symbol,
            )
            return await asyncio.to_thread(
                get_demo_data_service().get_technical_indicators,
                symbol=symbol,
                period=period,
                interval=interval,
                indicators=indicator_list,
                anchor_snapshot=anchor_snapshot,
            )

        hist = await asyncio.to_thread(
            _load_yfinance_history,
            symbol=symbol,
            period=period,
            interval=interval,
        )

        if hist.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No price data available for {symbol}",
            )

        # Compute indicators
        result_df = await asyncio.to_thread(
            TechnicalIndicatorEngine.compute_indicators, hist, indicators=indicator_list
        )
        return await asyncio.to_thread(
            _build_technical_indicator_response,
            symbol=symbol,
            period=period,
            indicator_list=indicator_list,
            result_df=result_df,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Technical indicator computation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Technical indicators failed: {str(e)}",
        )


@router.get("/vectorbt-backtest", response_model=VectorBTBacktestResult)
async def run_vectorbt_backtest(
    symbol: str = Query("SPX"),
    provider: str | None = Query(None),
    start_date: date = Query(...),
    end_date: date = Query(...),
    entry_threshold: float = Query(-1e9, allow_inf_nan=False),
    exit_threshold: float = Query(0.0, allow_inf_nan=False),
    initial_cash: float = Query(100_000.0, gt=0, allow_inf_nan=False),
    fees: float = Query(0.001, ge=0, lt=1, allow_inf_nan=False),
    slippage: float = Query(0.001, ge=0, lt=1, allow_inf_nan=False),
    position_size: float = Query(1.0, gt=0, le=1, allow_inf_nan=False),
    execution_delay_bars: int = Query(1, ge=1, le=30),
    demo: bool = Query(False),
) -> VectorBTBacktestResult:
    """Long-underlying simulation; signal-at-close executes at a later same-session close."""
    from app.core.vectorbt_backtester import VectorBTBacktester

    _validate_analytics_dates(start_date, end_date)
    if entry_threshold >= exit_threshold:
        raise HTTPException(
            status_code=400, detail="entry_threshold must be less than exit_threshold"
        )
    try:
        active_provider = ProviderRegistry.resolve_provider_name(provider)
        _backtest_instrument(active_provider, symbol, demo)
        prices, gex = await _analytics_frames(
            provider=active_provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            demo=demo,
        )
        result = VectorBTBacktester.run_gex_signal_backtest(
            price_data=_backtest_prices(prices, provider=active_provider, symbol=symbol),
            gex_data=gex,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            initial_cash=initial_cash,
            fees=fees,
            slippage=slippage,
            position_size=position_size,
            execution_delay_bars=execution_delay_bars,
        )
        payload = asdict(result)
        provenance = data_provenance(gex, provider=active_provider, symbol=symbol, synthetic=demo)
        provenance.quality_limitations.append(
            "Long-underlying simulation: sampled close fills, assumed fees/slippage and overnight positions; no verified executable quote or market-impact model."
        )
        payload.update(strategy="gex_long_underlying", provenance=provenance)
        return VectorBTBacktestResult(**payload)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
