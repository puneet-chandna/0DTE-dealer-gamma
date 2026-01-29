"""0DTE GEX Backend - Analytics API Endpoints.

Provides GEX-volatility analysis, backtesting, and summary statistics.
"""

import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from app.core.analytics import (
    TradingStrategy,
    VolatilityAnalyzer,
    generate_synthetic_gex_data,
    generate_synthetic_price_data,
)
from app.models.schemas import AnalyticsResult, BacktestResult, SummaryStatistics
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
    cache_key = f"analytics:summary:{start_date}:{end_date}"
    cached = cache.get_if_fresh(cache_key)
    if cached is not None:
        return cached

    try:
        # Generate synthetic data for demo
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        gex_data = generate_synthetic_gex_data(start_dt, end_dt)

        # Compute statistics
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
