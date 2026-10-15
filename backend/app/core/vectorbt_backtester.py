"""0DTE GEX Backend - VectorBT Backtesting Engine.

High-performance backtesting for GEX-based trading strategies
using vectorbt's vectorized portfolio simulation.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _session_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Use New York session dates; naive timestamps are interpreted as New York."""
    return (index.tz_convert("America/New_York") if index.tz is not None else index).normalize()


def _aligned_inputs(price_data: pd.DataFrame, gex_data: pd.DataFrame):
    """Align observed GEX without carrying it across sessions or missing price bars."""
    frames = []
    for name, frame, column in [
        ("price_data", price_data, "close"),
        ("gex_data", gex_data, "net_gex"),
    ]:
        if frame.empty:
            raise ValueError(f"{name} must not be empty")
        index = frame.index
        if not isinstance(index, pd.DatetimeIndex) or index.hasnans:
            raise ValueError(f"{name} must have a valid DatetimeIndex")
        if not index.is_unique or not index.is_monotonic_increasing:
            raise ValueError(f"{name} timestamps must be unique and strictly increasing")
        frame = frame.rename(columns=lambda c: str(c).lower())
        if not frame.columns.is_unique or column not in frame:
            raise ValueError(f"{name} must have a unique '{column}' column")
        if np.iscomplexobj(frame[column]):
            raise ValueError(f"{name}.{column} must be real-valued")
        try:
            values = frame[column].astype(float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name}.{column} must be numeric") from exc
        if not np.isfinite(values).all() or (column == "close" and (values <= 0).any()):
            raise ValueError(
                f"{name}.{column} must be finite" + (" and positive" if column == "close" else "")
            )
        frames.append(values)

    close, gex = frames
    if (close.index.tz is None) != (gex.index.tz is None):
        raise ValueError("price_data and gex_data must use compatible timestamp timezones")
    if gex.index.tz is not None:
        gex.index = gex.index.tz_convert(close.index.tz)
    sessions = _session_dates(close.index)
    deltas = close.index[1:] - close.index[:-1]
    same_session = sessions[1:] == sessions[:-1]
    within_session = deltas[same_session]
    if len(within_session) == 0:
        raise ValueError("At least two bars in one session are required to infer the bar interval")
    # Sorted modes make tied intervals deterministic, favoring the shorter delta.
    interval = pd.Series(within_session).mode().iloc[0]
    gaps = deltas != interval
    gap_starts = close.index[1:][same_session & gaps]
    union = gex.index.union(close.index)
    aligned = (
        gex.reindex(union)
        .groupby([_session_dates(union), gap_starts.searchsorted(union, side="right")])
        .ffill()
        .reindex(close.index)
    )
    runs = np.append(0, np.cumsum(~same_session | gaps))
    return close, aligned, runs, interval


@dataclass
class VectorBTResult:
    """Enhanced backtest results from vectorbt."""

    total_return: float
    sharpe_ratio: float | None
    sortino_ratio: float | None
    calmar_ratio: float | None
    max_drawdown: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float | None
    avg_trade_return: float
    best_trade: float
    worst_trade: float
    avg_trade_duration_minutes: float
    start_date: datetime
    end_date: datetime
    equity_curve: list[float]
    equity_timestamps: list[datetime] = field(default_factory=list)
    closed_trades: int = 0
    open_trades: int = 0
    bar_interval_minutes: float = 0.0
    initial_cash: float = 100_000.0
    fees: float = 0.001
    slippage: float = 0.001
    position_size: float = 1.0
    execution_delay_bars: int = 1


class VectorBTBacktester:
    """Backtesting engine powered by vectorbt.

    Simulates a directional long position in the underlying from intraday bars.
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
        position_size: float = 1.0,
        execution_delay_bars: int = 1,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
    ) -> VectorBTResult:
        """Simulate long underlying exposure, never options or long-volatility PnL.

        GEX and close-observed stop/target decisions fill at a later close in the
        same uninterrupted New York session. Price gaps cancel pending decisions
        and require fresh GEX; existing positions still mark to observed prices.
        Positions may carry overnight; stale GEX cannot.
        Stops are not guaranteed prices, and high/low bars are not used. Fees and
        adverse slippage apply on both orders; position_size is the fraction of
        available cash allocated including entry fees. Fractional units are used.

        Trade summaries use completed trades; total_trades includes open trades.
        Equity includes unrealized PnL. Undefined ratios are None. Risk ratios
        assume 252 sessions of 390 minutes, with zero risk-free return, and use
        the inferred bar interval. Costs and allocation are model assumptions.
        """
        parameters = {
            "entry_threshold": entry_threshold,
            "exit_threshold": exit_threshold,
            "initial_cash": initial_cash,
            "fees": fees,
            "slippage": slippage,
            "position_size": position_size,
        }
        if not all(np.isfinite(value) for value in parameters.values()):
            raise ValueError("Backtest parameters must be finite")
        if entry_threshold >= exit_threshold:
            raise ValueError("entry_threshold must be less than exit_threshold")
        if initial_cash <= 0 or not 0 < position_size <= 1:
            raise ValueError("initial_cash must be positive and position_size must be in (0, 1]")
        if not 0 <= fees < 1 or not 0 <= slippage < 1:
            raise ValueError("fees and slippage must be in [0, 1)")
        if (
            isinstance(execution_delay_bars, bool)
            or not isinstance(execution_delay_bars, int | np.integer)
            or execution_delay_bars < 1
        ):
            raise ValueError("execution_delay_bars must be a positive integer")
        if stop_loss_pct is not None and (
            not np.isfinite(stop_loss_pct) or not 0 < stop_loss_pct < 1
        ):
            raise ValueError("stop_loss_pct must be in (0, 1) when supplied")
        if take_profit_pct is not None and (
            not np.isfinite(take_profit_pct) or not 0 < take_profit_pct <= 1
        ):
            raise ValueError("take_profit_pct must be in (0, 1] when supplied")

        close, gex, runs, interval = _aligned_inputs(price_data, gex_data)
        entries = np.zeros(len(close), dtype=bool)
        exits = np.zeros(len(close), dtype=bool)
        in_position = False
        entry_price = 0.0
        entry_index = 0
        for i in range(execution_delay_bars, len(close)):
            observed = i - execution_delay_bars
            if runs[i] != runs[observed]:
                continue
            if not in_position:
                if gex.iloc[observed] < entry_threshold:
                    entries[i] = True
                    in_position = True
                    entry_price = close.iloc[i] * (1 + slippage)
                    entry_index = i
            else:
                # A stop can only use a close observed while the position existed.
                price_return = (close.iloc[observed] - entry_price) / entry_price
                stopped = (
                    observed >= entry_index
                    and stop_loss_pct is not None
                    and price_return <= -stop_loss_pct
                )
                targeted = (
                    observed >= entry_index
                    and take_profit_pct is not None
                    and price_return >= take_profit_pct
                )
                if gex.iloc[observed] > exit_threshold or stopped or targeted:
                    exits[i] = True
                    in_position = False

        import vectorbt as vbt

        pf = vbt.Portfolio.from_signals(
            close=close,
            entries=entries,
            exits=exits,
            direction="longonly",
            size=position_size,
            size_type="percent",
            init_cash=initial_cash,
            fees=fees,
            slippage=slippage,
            freq=interval,
            raise_reject=True,
        )
        equity = pf.value()
        closed = pf.trades.closed.records
        pnls = closed["pnl"].to_numpy()
        # Include entry fees in invested capital, unlike vectorbt's price-only basis.
        returns = pnls / (closed["size"] * closed["entry_price"] + closed["entry_fees"]).to_numpy()
        winning = int((pnls > 0).sum())
        losing = int((pnls < 0).sum())
        total = len(pf.trades.records)
        gross_profit = float(pnls[pnls > 0].sum())
        gross_loss = -float(pnls[pnls < 0].sum())
        durations = (
            close.index.take(closed["exit_idx"]) - close.index.take(closed["entry_idx"])
        ).total_seconds() / 60
        risk = pf.returns().vbt.returns(freq=interval, year_freq=pd.Timedelta(minutes=252 * 390))

        def finite_ratio(value: float) -> float | None:
            return float(value) if np.isfinite(value) else None

        points = np.linspace(0, len(equity) - 1, min(500, len(equity)), dtype=int)
        sampled = equity.iloc[points]
        return VectorBTResult(
            total_return=float(equity.iloc[-1] / initial_cash - 1),
            sharpe_ratio=finite_ratio(risk.sharpe_ratio()),
            sortino_ratio=finite_ratio(risk.sortino_ratio()),
            calmar_ratio=finite_ratio(risk.calmar_ratio()),
            max_drawdown=float(-(equity / equity.cummax() - 1).min()),
            total_trades=total,
            closed_trades=len(closed),
            open_trades=total - len(closed),
            winning_trades=winning,
            losing_trades=losing,
            win_rate=winning / len(closed) if len(closed) else 0.0,
            profit_factor=gross_profit / gross_loss if gross_loss > 0 else None,
            avg_trade_return=float(returns.mean()) if len(returns) else 0.0,
            best_trade=float(returns.max()) if len(returns) else 0.0,
            worst_trade=float(returns.min()) if len(returns) else 0.0,
            avg_trade_duration_minutes=float(np.mean(durations)) if len(durations) else 0.0,
            start_date=close.index[0].to_pydatetime(),
            end_date=close.index[-1].to_pydatetime(),
            equity_curve=sampled.tolist(),
            equity_timestamps=sampled.index.to_pydatetime().tolist(),
            bar_interval_minutes=interval.total_seconds() / 60,
            initial_cash=initial_cash,
            fees=fees,
            slippage=slippage,
            position_size=position_size,
            execution_delay_bars=int(execution_delay_bars),
        )

    @staticmethod
    def run_regime_comparison(
        price_data: pd.DataFrame,
        gex_data: pd.DataFrame,
        short_gamma_threshold: float = -1e9,
        long_gamma_threshold: float = 1e9,
        initial_cash: float = 100_000.0,
    ) -> dict:
        """Summarize next same-session returns conditioned on observed GEX.

        Splits the data into short gamma, neutral, and long gamma periods
        and computes return statistics for each.

        Args:
            price_data: DataFrame with 'close' column.
            gex_data: DataFrame with 'net_gex' column.
            short_gamma_threshold: Below this = short gamma.
            long_gamma_threshold: Above this = long gamma.
            initial_cash: Retained for compatibility; relative returns do not depend on capital.

        Returns:
            Dictionary with per-regime statistics.
        """
        if not np.isfinite(short_gamma_threshold) or not np.isfinite(long_gamma_threshold):
            raise ValueError("Regime thresholds must be finite")
        if short_gamma_threshold >= long_gamma_threshold:
            raise ValueError("short_gamma_threshold must be less than long_gamma_threshold")
        close, gex, runs, interval = _aligned_inputs(price_data, gex_data)
        # Attribute only the next contiguous return to GEX known at its start.
        returns = close.shift(-1) / close - 1
        contiguous = np.append(runs[:-1] == runs[1:], False)
        returns = returns.where(contiguous)
        regimes = {
            "short_gamma": returns[gex < short_gamma_threshold].dropna(),
            "neutral": returns[
                (gex >= short_gamma_threshold) & (gex <= long_gamma_threshold)
            ].dropna(),
            "long_gamma": returns[gex > long_gamma_threshold].dropna(),
        }
        annualization = pd.Timedelta(minutes=252 * 390) / interval
        results = {}
        for name, values in regimes.items():
            mean = float(values.mean()) if len(values) else 0.0
            std = float(values.std()) if len(values) > 1 else 0.0
            results[name] = {
                "count": len(values),
                "mean_return": mean,
                "std_return": std,
                "sharpe": mean / std * np.sqrt(annualization) if std > 0 else None,
                "total_return": float((1 + values).prod() - 1) if len(values) else 0.0,
            }
        return results
