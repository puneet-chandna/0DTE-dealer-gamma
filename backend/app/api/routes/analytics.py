"""0DTE GEX Backend - Analytics API Endpoints.

Provides GEX-volatility analysis, backtesting, and summary statistics.
"""

import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from fastapi import APIRouter, HTTPException, Query

from app.core import (
    VolatilityAnalyzer,
    TradingStrategy,
    ProviderRegistry,
    get_data_client,
    get_current_trading_date,
    is_market_open,
)
from app.core.analytics import (
    generate_synthetic_gex_data,
    generate_synthetic_price_data,
)
from app.core.demo_data import get_demo_data_service
from app.core.provider_registry import ProviderUnavailableError
from app.models.schemas import AnalyticsResult, BacktestResult, SummaryStatistics, IVSurfaceResponse
from app.services.cache import get_cache

logger = logging.getLogger(__name__)

router = APIRouter()

# Eastern Time timezone
ET = ZoneInfo("America/New_York")


@router.get("/gex-volatility", response_model=AnalyticsResult)
async def analyze_gex_volatility(
    start_date: date = Query(..., description="Start date for analysis"),
    end_date: date = Query(..., description="End date for analysis"),
) -> AnalyticsResult:
    """Analyze relationship between GEX and realized volatility.

    Performs a statistical analysis (Welch's t-test) to test the hypothesis
    that negative GEX (short gamma) corresponds to higher realized volatility.

    Note: Currently uses synthetic data for demonstration.
    Database storage will enable real historical analysis.
    """
    # Validate date range
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before or equal to end_date",
        )

    if (end_date - start_date).days > 365:
        raise HTTPException(
            status_code=400,
            detail="Date range cannot exceed 365 days",
        )

    if (end_date - start_date).days < 5:
        raise HTTPException(
            status_code=400,
            detail="Date range must be at least 5 days for statistical analysis",
        )

    # Check cache
    cache = get_cache()
    cache_key = f"analytics:gex-vol:{start_date}:{end_date}"
    cached = cache.get_if_fresh(cache_key)
    if cached is not None:
        return cached

    try:
        # Generate synthetic data for demo
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        gex_data = generate_synthetic_gex_data(start_dt, end_dt)
        price_data = generate_synthetic_price_data(start_dt, end_dt)

        # Perform analysis
        result = VolatilityAnalyzer.analyze_gex_volatility_relationship(
            gex_data=gex_data,
            price_data=price_data,
        )

        # Cache and return
        cache.set(cache_key, result)
        return result

    except ValueError as e:
        logger.warning(f"Analysis failed due to data issue: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to perform GEX-volatility analysis: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}",
        )


@router.get("/backtest", response_model=BacktestResult)
async def backtest_strategy(
    strategy: str = Query("volatility_breakout", description="Strategy name"),
    start_date: date = Query(..., description="Backtest start date"),
    end_date: date = Query(..., description="Backtest end date"),
    entry_threshold: float = Query(-1e9, description="GEX threshold for entry (dollars)"),
    exit_threshold: float = Query(0.0, description="GEX threshold for exit (dollars)"),
    stop_loss_pct: float = Query(0.02, description="Stop loss percentage (0.02 = 2%)"),
    take_profit_pct: float = Query(0.05, description="Take profit percentage (0.05 = 5%)"),
    demo: bool = Query(False, description="Return deterministic demo data"),
) -> BacktestResult:
    """Backtest trading strategy based on GEX signals.

    Supported strategies:
    - volatility_breakout: Enter long volatility when Net GEX < entry_threshold

    Note: Currently uses synthetic data for demonstration.
    """
    # Validate strategy
    if strategy not in ["volatility_breakout"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy: {strategy}. Supported: volatility_breakout",
        )

    # Validate date range
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before or equal to end_date",
        )

    if (end_date - start_date).days < 5:
        raise HTTPException(
            status_code=400,
            detail="Backtest period must be at least 5 days",
        )

    if (end_date - start_date).days > 365:
        raise HTTPException(
            status_code=400,
            detail="Backtest period cannot exceed 365 days",
        )

    # Validate thresholds
    if entry_threshold >= exit_threshold:
        raise HTTPException(
            status_code=400,
            detail="entry_threshold must be less than exit_threshold",
        )

    if stop_loss_pct <= 0 or stop_loss_pct > 0.5:
        raise HTTPException(
            status_code=400,
            detail="stop_loss_pct must be between 0 and 0.5 (50%)",
        )

    if take_profit_pct <= 0 or take_profit_pct > 1.0:
        raise HTTPException(
            status_code=400,
            detail="take_profit_pct must be between 0 and 1.0 (100%)",
        )

    try:
        # Generate synthetic data for demo
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        if demo:
            price_data, gex_data = get_demo_data_service().get_time_series(
                symbol="SPX",
                start_date=start_date,
                end_date=end_date,
            )
        else:
            gex_data = generate_synthetic_gex_data(start_dt, end_dt)
            price_data = generate_synthetic_price_data(start_dt, end_dt)

        # Run backtest
        result = TradingStrategy.volatility_breakout_strategy(
            gex_data=gex_data,
            price_data=price_data,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )

        return BacktestResult(
            total_trades=result.total_trades,
            winning_trades=result.winning_trades,
            losing_trades=result.losing_trades,
            win_rate=result.win_rate,
            total_return=result.total_return,
            average_return=result.average_return,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown=result.max_drawdown,
            profit_factor=result.profit_factor,
            average_trade_duration=result.average_trade_duration,
            start_date=result.start_date,
            end_date=result.end_date,
        )

    except ValueError as e:
        logger.warning(f"Backtest failed due to data issue: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to run backtest: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Backtest failed: {str(e)}",
        )


@router.get("/summary-statistics", response_model=SummaryStatistics)
async def get_summary_stats(
    start_date: Optional[date] = Query(None, description="Start date"),
    end_date: Optional[date] = Query(None, description="End date"),
    demo: bool = Query(False, description="Return deterministic demo data"),
) -> SummaryStatistics:
    """Get summary statistics of GEX over time period.

    If dates not provided, returns stats for last 30 days (synthetic data).

    Note: Currently uses synthetic data for demonstration.
    """
    # Default to last 30 days if not specified
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = date.today().replace(day=1)  # First of current month

    # Validate date range
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before or equal to end_date",
        )

    # Check cache
    cache = get_cache()
    cache_key = f"analytics:summary:{'demo' if demo else 'live'}:{start_date}:{end_date}"
    cached = cache.get_if_fresh(cache_key)
    if cached is not None:
        return cached

    try:
        if demo:
            result = get_demo_data_service().get_summary_statistics(
                symbol="SPX",
                start_date=start_date,
                end_date=end_date,
            )
        else:
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.max.time())
            gex_data = generate_synthetic_gex_data(start_dt, end_dt)
            result = VolatilityAnalyzer.compute_summary_statistics(gex_data)

        # Cache and return
        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Failed to compute summary statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Summary statistics failed: {str(e)}",
        )


# ============================================================================
# New Integration Endpoints
# ============================================================================


@router.get("/iv-surface", response_model=IVSurfaceResponse)
async def get_iv_surface(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    provider: Optional[str] = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    demo: bool = Query(False, description="Return deterministic demo data"),
) -> IVSurfaceResponse:
    """Get Implied Volatility Surface data for 3D charting.
    
    Creates a mock surface or true surface based on available options data.
    """
    from app.core.rate_provider import get_rate_provider
    from app.core.vollib_bridge import VolLibBridge

    try:
        if demo:
            return get_demo_data_service().get_iv_surface(symbol=symbol)

        data_client = get_data_client(provider)

        # In a real scenario, we'd fetch multiple expirations. 
        # For now, we'll fetch the nearest chain and generate a realistic surface from it.
        try:
            options_df, spot_price = await data_client.get_options_chain_for_gex(
                underlying=symbol
            )
        except Exception as e:
            logger.warning(f"Could not fetch live options for IV surface via {data_client.provider_name}: {e}")
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
            options_df["T"] = (
                (expiration - now).dt.total_seconds() / (365.25 * 24 * 3600)
            )
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
        if demo:
            indicator_list = [item.strip().upper() for item in indicators.split(",")]
            return get_demo_data_service().get_technical_indicators(
                symbol=symbol,
                period=period,
                interval=interval,
                indicators=indicator_list,
            )

        import yfinance as yf

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No price data available for {symbol}",
            )

        # Compute indicators
        indicator_list = [i.strip().upper() for i in indicators.split(",")]
        result_df = TechnicalIndicatorEngine.compute_indicators(
            hist, indicators=indicator_list
        )

        # Build response data
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
            if "bb_upper" in result_df.columns:
                point["bb_upper"] = None if pd.isna(row["bb_upper"]) else float(row["bb_upper"])
                point["bb_mid"] = None if pd.isna(row["bb_mid"]) else float(row["bb_mid"])
                point["bb_lower"] = None if pd.isna(row["bb_lower"]) else float(row["bb_lower"])
            data.append(point)

        return {
            "symbol": symbol,
            "period": period,
            "indicators": indicator_list,
            "data": data,
            "count": len(data),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Technical indicator computation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Technical indicators failed: {str(e)}",
        )


@router.get("/vectorbt-backtest")
async def run_vectorbt_backtest(
    start_date: date = Query(..., description="Backtest start date"),
    end_date: date = Query(..., description="Backtest end date"),
    entry_threshold: float = Query(-1e9, description="GEX entry threshold (dollars)"),
    exit_threshold: float = Query(0.0, description="GEX exit threshold (dollars)"),
    initial_cash: float = Query(100_000.0, description="Starting capital"),
    demo: bool = Query(False, description="Return deterministic demo data"),
) -> dict:
    """Run high-performance backtest using vectorbt.

    Strategy: Enter long when net GEX < entry_threshold (short gamma),
    exit when net GEX > exit_threshold.

    Note: Currently uses synthetic data for demonstration.
    """
    from app.core.vectorbt_backtester import VectorBTBacktester

    # Validate
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    if (end_date - start_date).days < 5:
        raise HTTPException(status_code=400, detail="Period must be at least 5 days")

    if (end_date - start_date).days > 365:
        raise HTTPException(status_code=400, detail="Period cannot exceed 365 days")

    try:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        if demo:
            price_data, gex_data = get_demo_data_service().get_time_series(
                symbol="SPX",
                start_date=start_date,
                end_date=end_date,
            )
        else:
            gex_data = generate_synthetic_gex_data(start_dt, end_dt)
            price_data = generate_synthetic_price_data(start_dt, end_dt)

        result = VectorBTBacktester.run_gex_signal_backtest(
            price_data=price_data,
            gex_data=gex_data,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            initial_cash=initial_cash,
        )

        return {
            "total_return": result.total_return,
            "sharpe_ratio": result.sharpe_ratio,
            "sortino_ratio": result.sortino_ratio,
            "calmar_ratio": result.calmar_ratio,
            "max_drawdown": result.max_drawdown,
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "avg_trade_return": result.avg_trade_return,
            "best_trade": result.best_trade,
            "worst_trade": result.worst_trade,
            "avg_trade_duration_minutes": result.avg_trade_duration_minutes,
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
            "equity_curve": result.equity_curve,
        }

    except Exception as e:
        logger.error(f"VectorBT backtest failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"VectorBT backtest failed: {str(e)}",
        )
