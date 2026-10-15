"""0DTE GEX Backend - Analytics Module.

Statistical analysis of GEX-volatility relationships and
backtesting of directional underlying strategies.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

from app.core.constants import LONG_GAMMA_THRESHOLD, SHORT_GAMMA_THRESHOLD
from app.models.schemas import AnalyticsResult, SummaryStatistics

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Results from backtesting a trading strategy."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    average_return: float
    sharpe_ratio: float | None
    max_drawdown: float
    profit_factor: float | None
    average_trade_duration: float  # in minutes
    start_date: datetime
    end_date: datetime
    equity_curve: list[float] = field(default_factory=list)
    equity_timestamps: list[datetime] = field(default_factory=list)
    closed_trades: int = 0
    open_trades: int = 0
    bar_interval_minutes: float = 0.0
    initial_cash: float = 100_000.0
    fees: float = 0.001
    slippage: float = 0.001
    position_size: float = 1.0
    execution_delay_bars: int = 1


class VolatilityAnalyzer:
    """
    Analyze relationship between GEX and realized volatility.

    Uses statistical tests to validate the hypothesis that
    negative GEX (short gamma) corresponds to higher volatility.
    """

    @staticmethod
    def calculate_realized_volatility(
        price_data: pd.DataFrame,
        window_minutes: int = 30,
        annualization_factor: float = 252 * 390,  # trading minutes per year
    ) -> pd.Series:
        """
        Calculate realized volatility from price data.

        Uses the standard deviation of log returns, annualized.

        Args:
            price_data: DataFrame with 'close' column and datetime index.
            window_minutes: Rolling window for volatility calculation.
            annualization_factor: Factor to annualize volatility.

        Returns:
            Series of realized volatility values.
        """
        if "close" not in price_data.columns:
            raise ValueError("price_data must have 'close' column")

        # Calculate log returns
        log_returns = np.log(price_data["close"] / price_data["close"].shift(1))

        # Calculate rolling standard deviation
        rolling_std = log_returns.rolling(window=window_minutes).std()

        # Annualize
        realized_vol = rolling_std * np.sqrt(annualization_factor)

        return realized_vol

    @staticmethod
    def analyze_gex_volatility_relationship(
        gex_data: pd.DataFrame,
        price_data: pd.DataFrame,
        negative_threshold: float = SHORT_GAMMA_THRESHOLD,
        positive_threshold: float = LONG_GAMMA_THRESHOLD,
    ) -> AnalyticsResult:
        """
        Perform statistical analysis of GEX-volatility relationship.

        Hypothesis Test:
        H0: Mean RV when GEX < threshold equals Mean RV when GEX > 0
        H1: Mean RV when GEX < threshold > Mean RV when GEX > 0

        Uses Welch's t-test for unequal variances.

        Args:
            gex_data: DataFrame with 'net_gex' column and datetime index.
            price_data: DataFrame with 'close' column and datetime index.
            negative_threshold: GEX threshold for "negative" classification.
            positive_threshold: GEX threshold for "positive" classification.

        Returns:
            AnalyticsResult with statistical test results.
        """
        # Validate inputs
        if gex_data.empty or price_data.empty:
            raise ValueError("gex_data and price_data must not be empty")

        if "net_gex" not in gex_data.columns:
            raise ValueError("gex_data must have 'net_gex' column")

        # Calculate realized volatility
        rv = VolatilityAnalyzer.calculate_realized_volatility(price_data)

        # Align data by timestamp
        merged = pd.merge(
            gex_data[["net_gex"]],
            pd.DataFrame({"rv": rv}),
            left_index=True,
            right_index=True,
            how="inner",
        )

        if merged.empty:
            raise ValueError("No overlapping data between gex_data and price_data")

        # Split by GEX regime
        negative_gex_mask = merged["net_gex"] < negative_threshold
        positive_gex_mask = merged["net_gex"] > positive_threshold

        rv_negative = merged.loc[negative_gex_mask, "rv"].dropna()
        rv_positive = merged.loc[positive_gex_mask, "rv"].dropna()

        if len(rv_negative) < 5 or len(rv_positive) < 5:
            logger.warning("Insufficient samples for statistical analysis")
            return AnalyticsResult(
                mean_rv_negative_gex=float(rv_negative.mean()) if len(rv_negative) > 0 else 0.0,
                mean_rv_positive_gex=float(rv_positive.mean()) if len(rv_positive) > 0 else 0.0,
                volatility_increase_pct=0.0,
                t_statistic=0.0,
                p_value=1.0,
                significant=False,
                sample_size_negative=len(rv_negative),
                sample_size_positive=len(rv_positive),
            )

        # Calculate means
        mean_rv_negative = float(rv_negative.mean())
        mean_rv_positive = float(rv_positive.mean())

        # Calculate volatility increase percentage
        if mean_rv_positive > 0:
            vol_increase_pct = ((mean_rv_negative - mean_rv_positive) / mean_rv_positive) * 100
        else:
            vol_increase_pct = 0.0

        # Perform Welch's t-test (one-tailed: negative GEX has higher vol)
        t_stat, p_value = stats.ttest_ind(
            rv_negative,
            rv_positive,
            equal_var=False,  # Welch's t-test
            alternative="greater",  # One-tailed: negative has higher vol
        )

        # Significance at 5% level
        significant = p_value < 0.05

        logger.info(
            f"GEX-Volatility Analysis: "
            f"Mean RV (neg GEX): {mean_rv_negative:.4f}, "
            f"Mean RV (pos GEX): {mean_rv_positive:.4f}, "
            f"Increase: {vol_increase_pct:.1f}%, "
            f"p-value: {p_value:.4f}"
        )

        return AnalyticsResult(
            mean_rv_negative_gex=mean_rv_negative,
            mean_rv_positive_gex=mean_rv_positive,
            volatility_increase_pct=vol_increase_pct,
            t_statistic=float(t_stat),
            p_value=float(p_value),
            significant=significant,
            sample_size_negative=len(rv_negative),
            sample_size_positive=len(rv_positive),
        )

    @staticmethod
    def compute_summary_statistics(
        gex_data: pd.DataFrame,
    ) -> SummaryStatistics:
        """
        Compute summary statistics for GEX data.

        Args:
            gex_data: DataFrame with 'net_gex' column.

        Returns:
            SummaryStatistics with mean, std, min, max, median, etc.
        """
        if gex_data.empty or "net_gex" not in gex_data.columns:
            return SummaryStatistics(
                mean_gex=0.0,
                std_gex=0.0,
                min_gex=0.0,
                max_gex=0.0,
                median_gex=0.0,
                pct_negative_days=0.0,
                sample_size=0,
            )

        gex = gex_data["net_gex"].dropna()

        return SummaryStatistics(
            mean_gex=float(gex.mean()),
            std_gex=float(gex.std()),
            min_gex=float(gex.min()),
            max_gex=float(gex.max()),
            median_gex=float(gex.median()),
            pct_negative_days=float((gex < 0).mean() * 100),
            sample_size=len(gex),
        )


class TradingStrategy:
    """Compatibility entry points for directional GEX-conditioned simulations."""

    @staticmethod
    def volatility_breakout_strategy(
        gex_data: pd.DataFrame,
        price_data: pd.DataFrame,
        entry_threshold: float = SHORT_GAMMA_THRESHOLD,
        exit_threshold: float = 0.0,
        stop_loss_pct: float = 0.02,
        take_profit_pct: float = 0.05,
        initial_cash: float = 100_000.0,
        fees: float = 0.001,
        slippage: float = 0.001,
        position_size: float = 1.0,
        execution_delay_bars: int = 1,
    ) -> BacktestResult:
        """Legacy strategy name for long underlying PnL with delayed close exits.

        Stops and targets observe signed close-to-entry returns and execute at
        the next eligible close. This does not simulate options or long volatility.
        """
        from app.core.vectorbt_backtester import VectorBTBacktester

        result = VectorBTBacktester.run_gex_signal_backtest(
            price_data=price_data,
            gex_data=gex_data,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            initial_cash=initial_cash,
            fees=fees,
            slippage=slippage,
            position_size=position_size,
            execution_delay_bars=execution_delay_bars,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )
        return BacktestResult(
            total_trades=result.total_trades,
            winning_trades=result.winning_trades,
            losing_trades=result.losing_trades,
            win_rate=result.win_rate,
            total_return=result.total_return,
            average_return=result.avg_trade_return,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown=result.max_drawdown,
            profit_factor=result.profit_factor,
            average_trade_duration=result.avg_trade_duration_minutes,
            start_date=result.start_date,
            end_date=result.end_date,
            equity_curve=result.equity_curve,
            equity_timestamps=result.equity_timestamps,
            closed_trades=result.closed_trades,
            open_trades=result.open_trades,
            bar_interval_minutes=result.bar_interval_minutes,
            initial_cash=result.initial_cash,
            fees=result.fees,
            slippage=result.slippage,
            position_size=result.position_size,
            execution_delay_bars=result.execution_delay_bars,
        )

    @staticmethod
    def regime_based_strategy(
        gex_data: pd.DataFrame,
        price_data: pd.DataFrame,
    ) -> dict:
        """
        Analyze returns by GEX regime.

        Splits data into short gamma, neutral, and long gamma regimes
        and calculates average returns for each.

        Args:
            gex_data: DataFrame with 'net_gex' column.
            price_data: DataFrame with 'close' column.

        Returns:
            Dictionary with regime-based statistics.
        """
        if gex_data.empty or price_data.empty:
            return {}
        from app.core.vectorbt_backtester import VectorBTBacktester

        comparison = VectorBTBacktester.run_regime_comparison(
            price_data,
            gex_data,
            short_gamma_threshold=SHORT_GAMMA_THRESHOLD,
            long_gamma_threshold=LONG_GAMMA_THRESHOLD,
        )
        return {
            name: {
                "mean": values["mean_return"],
                "std": values["std_return"],
                "count": values["count"],
            }
            for name, values in comparison.items()
        }


def generate_synthetic_gex_data(
    start_date: datetime,
    end_date: datetime,
    freq: str = "5min",
) -> pd.DataFrame:
    """
    Generate synthetic GEX data for testing.

    Creates realistic-looking GEX data with mean-reverting behavior
    and occasional short gamma events.

    Args:
        start_date: Start of date range.
        end_date: End of date range.
        freq: Frequency of data points.

    Returns:
        DataFrame with synthetic GEX data.
    """
    # Create date range (market hours only)
    date_range = pd.date_range(start=start_date, end=end_date, freq=freq)

    # Filter to market hours (9:30 AM - 4:00 PM ET)
    date_range = date_range[
        (date_range.hour > 9) | ((date_range.hour == 9) & (date_range.minute >= 30))
    ]
    date_range = date_range[date_range.hour < 16]

    n = len(date_range)

    # Generate mean-reverting GEX with occasional negative spikes
    np.random.seed(42)
    mean_gex = 0.5e9  # $500M average (long gamma)
    std_gex = 0.8e9

    gex = np.zeros(n)
    gex[0] = mean_gex

    for i in range(1, n):
        # Mean reversion
        reversion = 0.1 * (mean_gex - gex[i - 1])
        # Random shock
        shock = np.random.normal(0, std_gex * 0.1)
        # Occasional large moves
        if np.random.random() < 0.02:
            shock += np.random.choice([-1, 1]) * std_gex * 0.5

        gex[i] = gex[i - 1] + reversion + shock

    return pd.DataFrame({"net_gex": gex, "timestamp": date_range}).set_index("timestamp")


def generate_synthetic_price_data(
    start_date: datetime,
    end_date: datetime,
    freq: str = "5min",
    initial_price: float = 5900.0,
) -> pd.DataFrame:
    """
    Generate synthetic price data for testing.

    Creates realistic-looking price data with variable volatility.

    Args:
        start_date: Start of date range.
        end_date: End of date range.
        freq: Frequency of data points.
        initial_price: Starting price.

    Returns:
        DataFrame with synthetic price data.
    """
    # Create date range (market hours only)
    date_range = pd.date_range(start=start_date, end=end_date, freq=freq)

    # Filter to market hours
    date_range = date_range[
        (date_range.hour > 9) | ((date_range.hour == 9) & (date_range.minute >= 30))
    ]
    date_range = date_range[date_range.hour < 16]

    n = len(date_range)

    # Generate price with geometric Brownian motion
    np.random.seed(43)
    daily_vol = 0.15  # 15% annualized
    dt = 1 / (252 * 78)  # 5-minute intervals
    vol_per_interval = daily_vol * np.sqrt(dt)

    returns = np.random.normal(0, vol_per_interval, n)
    log_prices = np.log(initial_price) + np.cumsum(returns)
    prices = np.exp(log_prices)

    # Add high/low (simplified)
    high = prices * (1 + np.abs(np.random.normal(0, 0.001, n)))
    low = prices * (1 - np.abs(np.random.normal(0, 0.001, n)))

    return pd.DataFrame(
        {
            "close": prices,
            "high": high,
            "low": low,
            "timestamp": date_range,
        }
    ).set_index("timestamp")
