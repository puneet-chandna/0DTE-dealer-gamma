"""0DTE GEX Backend - VectorBT Backtesting Engine.

High-performance backtesting for GEX-based trading strategies
using vectorbt's vectorized portfolio simulation.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class VectorBTResult:
    """Enhanced backtest results from vectorbt."""

    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    avg_trade_return: float
    best_trade: float
    worst_trade: float
    avg_trade_duration_minutes: float
    start_date: datetime
    end_date: datetime
    equity_curve: list[float]


class VectorBTBacktester:
    """Backtesting engine powered by vectorbt.

    Converts GEX thresholds into entry/exit signals and runs
    a vectorized portfolio simulation for maximum performance
    on intraday (1-minute) data.
    """

    @staticmethod
    def run_gex_signal_backtest(
        price_data: pd.DataFrame,
        gex_data: pd.DataFrame,
        entry_threshold: float = -1e9,
        exit_threshold: float = 0.0,
        initial_cash: float = 100_000.0,
        fees: float = 0.001,
        slippage: float = 0.001,
    ) -> VectorBTResult:
        """Run a GEX-based signal backtest using vectorbt.

        Strategy:
        - ENTER long when net GEX drops below entry_threshold (short gamma regime)
        - EXIT when net GEX rises above exit_threshold (back to neutral/long gamma)

        The hypothesis: short gamma regimes lead to volatile moves that can
        be captured by being long.

        Args:
            price_data: DataFrame with 'close' column and DatetimeIndex.
            gex_data: DataFrame with 'net_gex' column and DatetimeIndex.
            entry_threshold: GEX level to enter (default: -$1B).
            exit_threshold: GEX level to exit (default: $0).
            initial_cash: Starting capital (default: $100K).
            fees: Transaction fee percentage (default: 0.1%).
            slippage: Slippage percentage (default: 0.1%).

        Returns:
            VectorBTResult with comprehensive metrics and equity curve.
        """
        import vectorbt as vbt

        # Normalize column names
        price_df = price_data.copy()
        price_df.columns = [c.lower() for c in price_df.columns]

        gex_df = gex_data.copy()
        gex_df.columns = [c.lower() for c in gex_df.columns]

        # Align data on common timestamps
        close = price_df["close"]
        gex = gex_df["net_gex"].reindex(close.index, method="ffill")

        # Generate boolean entry/exit signals
        entries = gex < entry_threshold
        exits = gex > exit_threshold

        # Clean signals: no entry while already in position
        # vectorbt handles this with from_signals
        pf = vbt.Portfolio.from_signals(
            close=close,
            entries=entries,
            exits=exits,
            init_cash=initial_cash,
            fees=fees,
            slippage=slippage,
            freq="1min",  # Assume minute-level data
        )

        # Extract metrics
        stats = pf.stats()
        trades = pf.trades.records_readable if len(pf.trades.records) > 0 else None

        total_trades = int(stats.get("Total Trades", 0))
        winning_trades = int(stats.get("Win Rate [%]", 0) / 100 * total_trades) if total_trades > 0 else 0
        losing_trades = total_trades - winning_trades

        # Equity curve (downsampled for API response)
        equity = pf.value()
        if len(equity) > 500:
            # Downsample to ~500 points
            step = max(1, len(equity) // 500)
            equity_curve = equity.iloc[::step].tolist()
        else:
            equity_curve = equity.tolist()

        # Safe metric extraction with fallbacks
        def safe_get(key: str, default: float = 0.0) -> float:
            val = stats.get(key, default)
            # Handle pandas Timedelta (e.g. "Avg Winning Trade Duration")
            if isinstance(val, pd.Timedelta):
                return val.total_seconds() / 60.0  # Convert to minutes
            # Handle NaT / None
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return default
            if isinstance(val, type(pd.NaT)):
                return default
            # Handle string percentages
            if isinstance(val, str):
                try:
                    val = float(val.rstrip("%")) / 100
                except (ValueError, AttributeError):
                    return default
            # Final conversion
            try:
                result = float(val)
                return result if np.isfinite(result) else default
            except (TypeError, ValueError):
                return default

        return VectorBTResult(
            total_return=safe_get("Total Return [%]") / 100,
            sharpe_ratio=safe_get("Sharpe Ratio"),
            sortino_ratio=safe_get("Sortino Ratio"),
            calmar_ratio=safe_get("Calmar Ratio"),
            max_drawdown=safe_get("Max Drawdown [%]") / 100,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=safe_get("Win Rate [%]") / 100,
            profit_factor=safe_get("Profit Factor", 1.0),
            avg_trade_return=safe_get("Avg Winning Trade [%]") / 100,
            best_trade=safe_get("Best Trade [%]") / 100,
            worst_trade=safe_get("Worst Trade [%]") / 100,
            avg_trade_duration_minutes=safe_get("Avg Winning Trade Duration"),
            start_date=close.index[0].to_pydatetime() if hasattr(close.index[0], "to_pydatetime") else close.index[0],
            end_date=close.index[-1].to_pydatetime() if hasattr(close.index[-1], "to_pydatetime") else close.index[-1],
            equity_curve=equity_curve,
        )

    @staticmethod
    def run_regime_comparison(
        price_data: pd.DataFrame,
        gex_data: pd.DataFrame,
        short_gamma_threshold: float = -1e9,
        long_gamma_threshold: float = 1e9,
        initial_cash: float = 100_000.0,
    ) -> dict:
        """Compare buy-and-hold performance during different GEX regimes.

        Splits the data into short gamma, neutral, and long gamma periods
        and computes return statistics for each.

        Args:
            price_data: DataFrame with 'close' column.
            gex_data: DataFrame with 'net_gex' column.
            short_gamma_threshold: Below this = short gamma.
            long_gamma_threshold: Above this = long gamma.
            initial_cash: Starting capital.

        Returns:
            Dictionary with per-regime statistics.
        """
        price_df = price_data.copy()
        price_df.columns = [c.lower() for c in price_df.columns]

        gex_df = gex_data.copy()
        gex_df.columns = [c.lower() for c in gex_df.columns]

        close = price_df["close"]
        gex = gex_df["net_gex"].reindex(close.index, method="ffill")

        # Classify regimes
        returns = close.pct_change().dropna()
        gex_aligned = gex.reindex(returns.index, method="ffill")

        regimes = {
            "short_gamma": returns[gex_aligned < short_gamma_threshold],
            "neutral": returns[
                (gex_aligned >= short_gamma_threshold)
                & (gex_aligned <= long_gamma_threshold)
            ],
            "long_gamma": returns[gex_aligned > long_gamma_threshold],
        }

        results = {}
        for regime_name, regime_returns in regimes.items():
            if len(regime_returns) < 2:
                results[regime_name] = {
                    "count": len(regime_returns),
                    "mean_return": 0.0,
                    "std_return": 0.0,
                    "sharpe": 0.0,
                    "total_return": 0.0,
                }
                continue

            mean_ret = float(regime_returns.mean())
            std_ret = float(regime_returns.std())
            sharpe = mean_ret / std_ret * np.sqrt(252 * 390) if std_ret > 0 else 0.0

            results[regime_name] = {
                "count": len(regime_returns),
                "mean_return": mean_ret,
                "std_return": std_ret,
                "sharpe": sharpe,
                "total_return": float((1 + regime_returns).prod() - 1),
            }

        return results
