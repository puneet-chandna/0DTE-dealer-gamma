"""0DTE GEX Backend - Analytics Module.

Statistical analysis of GEX-volatility relationships and
backtesting of volatility-based trading strategies.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from app.core.constants import SHORT_GAMMA_THRESHOLD, LONG_GAMMA_THRESHOLD
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
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    average_trade_duration: float  # in minutes
    start_date: datetime
    end_date: datetime


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
    """
    Backtesting trading strategies based on GEX signals.

    Primary strategy: Enter long volatility when Net GEX < threshold.
    """

    @staticmethod
    def volatility_breakout_strategy(
        gex_data: pd.DataFrame,
        price_data: pd.DataFrame,
        entry_threshold: float = SHORT_GAMMA_THRESHOLD,
        exit_threshold: float = 0.0,
        stop_loss_pct: float = 0.02,  # 2% stop loss
        take_profit_pct: float = 0.05,  # 5% take profit
    ) -> BacktestResult:
        """
        Backtest volatility breakout strategy conditioned on GEX.

        Strategy:
        - Enter long volatility (long VIX, long straddle, etc.) when Net GEX < threshold
        - Exit when Net GEX > exit_threshold or stop/target hit
        - Assumes we can capture a fraction of the realized move

        Args:
            gex_data: DataFrame with 'net_gex' column and datetime index.
            price_data: DataFrame with 'close', 'high', 'low' columns and datetime index.
            entry_threshold: GEX threshold to enter trade.
            exit_threshold: GEX threshold to exit trade.
            stop_loss_pct: Stop loss percentage.
            take_profit_pct: Take profit percentage.

        Returns:
            BacktestResult with strategy performance metrics.
        """
        # Validate inputs
        if gex_data.empty or price_data.empty:
            raise ValueError("gex_data and price_data must not be empty")

        # Align data
        merged = pd.merge(
            gex_data[["net_gex"]],
            price_data[["close", "high", "low"]] if "high" in price_data.columns else price_data[["close"]],
            left_index=True,
            right_index=True,
            how="inner",
        )

        if len(merged) < 10:
            raise ValueError("Insufficient data for backtesting")

        # Track trades
        trades = []
        in_trade = False
        entry_price = 0.0
        entry_time = None
        entry_idx = 0

        for i, (idx, row) in enumerate(merged.iterrows()):
            net_gex = row["net_gex"]
            close = row["close"]

            if not in_trade:
                # Check entry condition
                if net_gex < entry_threshold:
                    in_trade = True
                    entry_price = close
                    entry_time = idx
                    entry_idx = i
            else:
                # Check exit conditions
                pnl_pct = (close - entry_price) / entry_price

                # For volatility strategy, we profit from moves in either direction
                # Simplified: use absolute return as proxy
                abs_pnl_pct = abs(pnl_pct)

                exit_trade = False
                exit_reason = ""

                # Stop loss
                if abs_pnl_pct < -stop_loss_pct:
                    exit_trade = True
                    exit_reason = "stop_loss"

                # Take profit
                elif abs_pnl_pct >= take_profit_pct:
                    exit_trade = True
                    exit_reason = "take_profit"

                # GEX exit signal
                elif net_gex > exit_threshold:
                    exit_trade = True
                    exit_reason = "gex_exit"

                if exit_trade:
                    # Calculate trade duration (approximate by index difference)
                    duration = i - entry_idx

                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": idx,
                        "entry_price": entry_price,
                        "exit_price": close,
                        "pnl_pct": abs_pnl_pct,  # Volatility strategy profits from move magnitude
                        "duration": duration,
                        "exit_reason": exit_reason,
                    })

                    in_trade = False
                    entry_price = 0.0
                    entry_time = None

        # Calculate metrics
        if not trades:
            return BacktestResult(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_return=0.0,
                average_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                profit_factor=0.0,
                average_trade_duration=0.0,
                start_date=merged.index[0],
                end_date=merged.index[-1],
            )

        trades_df = pd.DataFrame(trades)
        returns = trades_df["pnl_pct"].values

        # Basic metrics
        total_trades = len(trades)
        winning_trades = int((returns > 0).sum())
        losing_trades = int((returns < 0).sum())
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        # Return metrics
        total_return = float(returns.sum())
        average_return = float(returns.mean())

        # Sharpe ratio (simplified, assuming risk-free rate = 0)
        if returns.std() > 0:
            sharpe_ratio = float(returns.mean() / returns.std() * np.sqrt(252))  # Annualized
        else:
            sharpe_ratio = 0.0

        # Max drawdown
        cumulative_returns = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdowns = cumulative_returns - running_max
        max_drawdown = float(np.abs(drawdowns.min())) if len(drawdowns) > 0 else 0.0

        # Profit factor
        gross_profit = float(returns[returns > 0].sum()) if (returns > 0).any() else 0.0
        gross_loss = float(np.abs(returns[returns < 0].sum())) if (returns < 0).any() else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Average trade duration
        average_trade_duration = float(trades_df["duration"].mean())

        return BacktestResult(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_return=total_return,
            average_return=average_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            profit_factor=profit_factor,
            average_trade_duration=average_trade_duration,
            start_date=merged.index[0],
            end_date=merged.index[-1],
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
        merged = pd.merge(
            gex_data[["net_gex"]],
            price_data[["close"]],
            left_index=True,
            right_index=True,
            how="inner",
        )

        if merged.empty:
            return {}

        # Calculate forward returns
        merged["fwd_return"] = merged["close"].pct_change().shift(-1)

        # Define regimes
        merged["regime"] = "neutral"
        merged.loc[merged["net_gex"] < SHORT_GAMMA_THRESHOLD, "regime"] = "short_gamma"
        merged.loc[merged["net_gex"] > LONG_GAMMA_THRESHOLD, "regime"] = "long_gamma"

        # Group by regime
        regime_stats = merged.groupby("regime")["fwd_return"].agg(
            ["mean", "std", "count"]
        ).to_dict("index")

        return regime_stats


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

    return pd.DataFrame(
        {"net_gex": gex, "timestamp": date_range}
    ).set_index("timestamp")


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
