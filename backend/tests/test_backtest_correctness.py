"""Hand-calculated checks for executable, directional underlying backtests."""

import numpy as np
import pandas as pd
import pytest

from app.core.analytics import TradingStrategy
from app.core.vectorbt_backtester import VectorBTBacktester


def frames(prices, gex, timestamps=None):
    index = (
        pd.DatetimeIndex(timestamps)
        if timestamps is not None
        else pd.date_range(
            "2025-01-15 09:30", periods=len(prices), freq="5min", tz="America/New_York"
        )
    )
    return pd.DataFrame({"close": prices}, index=index), pd.DataFrame({"net_gex": gex}, index=index)


def run(prices, gex, **kwargs):
    price_data, gex_data = frames(prices, gex)
    return VectorBTBacktester.run_gex_signal_backtest(
        price_data, gex_data, fees=0, slippage=0, **kwargs
    )


def test_signal_fills_at_next_close_not_the_observed_close():
    # Buy at 110, sell at 121: 10%. Same-bar fills would buy 100 and sell 99.
    result = run([100, 110, 99, 121], [-2e9, -2e9, 2e9, 2e9])
    assert result.total_return == pytest.approx(0.10)
    assert result.avg_trade_return == pytest.approx(0.10)


def test_legacy_long_underlying_loses_on_a_falling_price():
    price_data, gex_data = frames([100, 100, 90, 90] + [90] * 6, [-2e9, -2e9] + [2e9] * 8)
    result = TradingStrategy.volatility_breakout_strategy(
        gex_data, price_data, stop_loss_pct=0.5, take_profit_pct=0.5
    )
    assert result.total_return < 0
    assert result.losing_trades == 1
    assert result.winning_trades == 0


def test_close_observed_stop_executes_on_the_following_bar():
    price_data, gex_data = frames([100, 100, 90, 80] + [80] * 6, [-2e9, -2e9] + [0] * 8)
    result = TradingStrategy.volatility_breakout_strategy(
        gex_data,
        price_data,
        stop_loss_pct=0.05,
        take_profit_pct=0.5,
        fees=0,
        slippage=0,
    )
    assert result.total_return == pytest.approx(-0.20)
    assert result.average_trade_duration == pytest.approx(10.0)


def test_exact_ten_percent_stop_is_not_lost_to_return_subtraction_rounding():
    result = run([100, 100, 90, 80], [-2e9, -2e9, 0, 0], stop_loss_pct=0.1)
    assert result.closed_trades == 1
    assert result.open_trades == 0
    assert result.avg_trade_return == pytest.approx(-0.2)


def test_close_observed_target_executes_on_the_following_bar():
    price_data, gex_data = frames([100, 100, 110, 120] + [120] * 6, [-2e9, -2e9] + [0] * 8)
    result = TradingStrategy.volatility_breakout_strategy(
        gex_data,
        price_data,
        stop_loss_pct=0.05,
        take_profit_pct=0.05,
        fees=0,
        slippage=0,
    )
    assert result.total_return == pytest.approx(0.20)
    assert result.total_trades == 1


def test_legacy_accepts_the_existing_one_hundred_percent_target_boundary():
    price_data, gex_data = frames([100, 100, 250, 250], [-2e9, -2e9, 0, 0])
    result = TradingStrategy.volatility_breakout_strategy(
        gex_data,
        price_data,
        take_profit_pct=1.0,
        fees=0,
        slippage=0,
    )
    assert result.total_return == pytest.approx(1.5)


def test_costs_and_half_allocation_are_charged_on_both_orders():
    price_data, gex_data = frames([100] * 4, [-2e9, -2e9, 2e9, 2e9])
    result = VectorBTBacktester.run_gex_signal_backtest(
        price_data,
        gex_data,
        initial_cash=1000,
        fees=0.01,
        slippage=0.02,
        position_size=0.5,
    )
    # Spend 500 incl fees buying at 102, receive shares * 98 * .99 selling.
    assert result.equity_curve[-1] == pytest.approx(970.879440885265)
    assert result.avg_trade_return == pytest.approx(-0.05824111822947001)
    assert result.losing_trades == 1


def test_open_trade_is_marked_to_market_but_not_counted_as_a_completed_loss():
    result = run([100, 100, 80, 90], [-2e9] * 4)
    assert result.total_return == pytest.approx(-0.10)
    assert result.max_drawdown == pytest.approx(0.20)
    assert result.equity_curve == pytest.approx([100000, 100000, 80000, 90000])
    assert result.total_trades == 1
    assert result.closed_trades == 0
    assert result.open_trades == 1
    assert result.losing_trades == 0
    assert result.avg_trade_return == 0


def test_first_closed_loss_contributes_to_drawdown():
    result = run([100, 100, 90, 90], [-2e9, -2e9, 2e9, 2e9])
    assert result.max_drawdown == pytest.approx(0.10)
    assert result.losing_trades == 1


def test_trade_average_includes_losses_and_duration_uses_actual_minutes():
    # Buy100->sell120 then buy100->sell90. Equity compounds to108000.
    result = run(
        [100, 100, 100, 120, 100, 100, 90, 90, 90],
        [-2e9, -2e9, 2e9, 2e9, -2e9, -2e9, -2e9, 2e9, 2e9],
    )
    assert result.total_return == pytest.approx(0.08)
    assert result.avg_trade_return == pytest.approx(0.05)
    assert result.win_rate == pytest.approx(0.5)
    assert result.winning_trades == result.losing_trades == 1
    assert result.avg_trade_duration_minutes == pytest.approx(12.5)
    assert result.best_trade == pytest.approx(0.2)
    assert result.worst_trade == pytest.approx(-0.1)
    assert result.bar_interval_minutes == 5


def test_last_bar_signal_cannot_fill_in_the_future():
    result = run([100, 100, 100, 100], [2e9, 2e9, 2e9, -2e9])
    assert result.total_trades == 0
    assert result.total_return == 0


def test_undefined_risk_and_profit_ratios_are_null_not_zero_or_infinity():
    result = run([100] * 4, [2e9] * 4)
    assert result.sharpe_ratio is None
    assert result.sortino_ratio is None
    assert result.calmar_ratio is None
    assert result.profit_factor is None


def test_all_winning_trades_have_undefined_profit_factor():
    result = run([100, 100, 110, 110], [-2e9, -2e9, 2e9, 2e9])
    assert result.profit_factor is None


def test_configured_execution_delay_changes_the_fill_bar():
    result = run([100, 110, 100, 120, 90], [-2e9, 0, 2e9, 2e9, 2e9], execution_delay_bars=2)
    # Delay two bars: buy100, then sell90.
    assert result.total_return == pytest.approx(-0.1)


def test_signals_do_not_fill_across_sessions():
    timestamps = ["2025-01-15 15:55", "2025-01-16 09:30", "2025-01-16 09:35"]
    prices, gex = frames([100, 110, 120], [-2e9, 0, 0], timestamps)
    result = VectorBTBacktester.run_gex_signal_backtest(prices, gex, fees=0, slippage=0)
    assert result.total_trades == 0


def test_gex_forward_fill_does_not_reuse_yesterdays_signal():
    timestamps = ["2025-01-15 15:50", "2025-01-15 15:55", "2025-01-16 09:30", "2025-01-16 09:35"]
    prices, gex = frames([100, 100, 110, 120], [2e9, -2e9, 0, 0], timestamps)
    result = VectorBTBacktester.run_gex_signal_backtest(prices, gex.iloc[:2], fees=0, slippage=0)
    assert result.total_trades == 0


def test_carried_position_duration_includes_the_overnight_holding_period():
    timestamps = ["2025-01-15 15:50", "2025-01-15 15:55", "2025-01-16 09:30", "2025-01-16 09:35"]
    prices, gex = frames([100, 100, 110, 110], [-2e9, -2e9, 2e9, 2e9], timestamps)
    result = VectorBTBacktester.run_gex_signal_backtest(prices, gex, fees=0, slippage=0)
    assert result.avg_trade_duration_minutes == pytest.approx(1060)


def test_future_gex_observation_does_not_backfill_an_entry():
    prices, gex = frames([100, 100, 110, 120], [-2e9] * 4)
    result = VectorBTBacktester.run_gex_signal_backtest(prices, gex.iloc[-1:], fees=0, slippage=0)
    assert result.total_trades == 0


@pytest.mark.parametrize(
    "bad_prices", [[100, 0, 100], [100, -1, 100], [100, np.nan, 100], [100, np.inf, 100]]
)
def test_rejects_non_positive_or_non_finite_prices(bad_prices):
    with pytest.raises(ValueError):
        run(bad_prices, [-2e9] * 3)


@pytest.mark.parametrize("gex", [[0, np.nan, 0], [0, np.inf, 0]])
def test_rejects_non_finite_gex_observations(gex):
    with pytest.raises(ValueError):
        run([100] * 3, gex)


@pytest.mark.parametrize("column", ["close", "net_gex"])
def test_rejects_complex_observations_instead_of_discarding_imaginary_values(column):
    price_data, gex_data = frames([100] * 3, [-2e9] * 3)
    frame = price_data if column == "close" else gex_data
    frame[column] = frame[column].astype(complex) + 1j
    with pytest.raises(ValueError):
        VectorBTBacktester.run_gex_signal_backtest(price_data, gex_data)


def test_rejects_unsorted_gex_instead_of_silently_looking_ahead():
    prices, gex = frames([100] * 3, [-2e9] * 3)
    with pytest.raises(ValueError):
        VectorBTBacktester.run_gex_signal_backtest(prices, gex.iloc[::-1])


def test_sharpe_annualizes_five_minute_bar_returns_as_five_minutes():
    # Equity returns are 0, 0, .1, -1/11; annualize their sample std with252*78.
    result = run([100, 100, 110, 100], [-2e9] * 4)
    assert result.sharpe_ratio == pytest.approx(4.085995195590892)


@pytest.mark.parametrize(
    "timestamps",
    [
        ["2025-01-15 09:30", "2025-01-15 09:30", "2025-01-15 09:35"],
        ["2025-01-15 09:35", "2025-01-15 09:30", "2025-01-15 09:40"],
    ],
)
def test_rejects_duplicate_or_unsorted_bar_times(timestamps):
    price_data, gex_data = frames([100] * 3, [-2e9] * 3, timestamps)
    with pytest.raises(ValueError):
        VectorBTBacktester.run_gex_signal_backtest(price_data, gex_data)


def test_missing_minute_bars_use_the_modal_interval_instead_of_the_first_gap():
    timestamps = [f"2025-01-15 09:{minute}" for minute in [30, 33, 34, 35, 36]]
    prices, gex = frames([100, 110, 100, 120, 100], [0, -2e9, 2e9, 2e9, 2e9], timestamps)
    result = VectorBTBacktester.run_gex_signal_backtest(prices, gex, fees=0, slippage=0)
    assert result.bar_interval_minutes == 1
    assert result.closed_trades == 1
    assert result.total_return == pytest.approx(0.2)


def test_modal_interval_ties_choose_the_shorter_delta():
    timestamps = [f"2025-01-15 09:{minute}" for minute in [30, 32, 33]]
    prices, gex = frames([100, 100, 100], [-2e9, 0, 0], timestamps)
    result = VectorBTBacktester.run_gex_signal_backtest(prices, gex, fees=0, slippage=0)
    assert result.bar_interval_minutes == 1
    assert result.total_trades == 0


def test_interval_inference_ignores_overnight_gaps():
    timestamps = [
        "2025-01-15 15:58",
        "2025-01-15 15:59",
        "2025-01-16 09:30",
        "2025-01-16 09:32",
        "2025-01-16 09:33",
    ]
    prices, gex = frames([100] * 5, [0] * 5, timestamps)
    result = VectorBTBacktester.run_gex_signal_backtest(prices, gex, fees=0, slippage=0)
    assert result.bar_interval_minutes == 1


@pytest.mark.parametrize(
    "timestamps", [["2025-01-15 09:30"], ["2025-01-15 09:30", "2025-01-16 09:30"]]
)
def test_interval_inference_still_requires_a_within_session_delta(timestamps):
    prices, gex = frames([100] * len(timestamps), [0] * len(timestamps), timestamps)
    with pytest.raises(ValueError, match="At least two bars in one session"):
        VectorBTBacktester.run_gex_signal_backtest(prices, gex)


@pytest.mark.parametrize("delay", [1, 2])
def test_delayed_entry_is_canceled_when_a_price_bar_is_missing(delay):
    timestamps = [f"2025-01-15 09:{minute}" for minute in [30, 31, 33, 34, 35, 36]]
    signals = [0] * 6
    signals[2 - delay] = -2e9
    prices, gex = frames([100] * 6, signals, timestamps)
    result = VectorBTBacktester.run_gex_signal_backtest(
        prices, gex, execution_delay_bars=delay, fees=0, slippage=0
    )
    assert result.total_trades == 0


def test_delay_cannot_cross_offsetting_irregular_intervals():
    timestamps = [
        "2025-01-15 09:30",
        "2025-01-15 09:30:30",
        "2025-01-15 09:32",
        "2025-01-15 09:33",
        "2025-01-15 09:34",
        "2025-01-15 09:35",
    ]
    prices, gex = frames([100] * 6, [-2e9, 0, 0, 0, 0, 0], timestamps)
    result = VectorBTBacktester.run_gex_signal_backtest(
        prices, gex, execution_delay_bars=2, fees=0, slippage=0
    )
    assert result.bar_interval_minutes == 1
    assert result.total_trades == 0


@pytest.mark.parametrize(
    "observed_price,signal,kwargs",
    [(100, 2e9, {}), (90, 0, {"stop_loss_pct": 0.1}), (110, 0, {"take_profit_pct": 0.1})],
)
def test_delayed_exit_cannot_jump_a_gap(observed_price, signal, kwargs):
    timestamps = [f"2025-01-15 09:{minute}" for minute in [30, 31, 32, 34, 35, 36]]
    prices, gex = frames(
        [100, 100, observed_price, 100, 105, 105], [-2e9, 0, signal, 0, 0, 0], timestamps
    )
    result = VectorBTBacktester.run_gex_signal_backtest(prices, gex, fees=0, slippage=0, **kwargs)
    assert result.open_trades == 1
    assert result.closed_trades == 0
    assert result.total_return == pytest.approx(0.05)


def test_open_position_marks_the_price_change_across_a_missing_bar():
    timestamps = [f"2025-01-15 09:{minute}" for minute in [30, 31, 33, 34, 35]]
    prices, gex = frames([100, 100, 80, 90, 90], [-2e9, 0, 0, 0, 0], timestamps)
    result = VectorBTBacktester.run_gex_signal_backtest(prices, gex, fees=0, slippage=0)
    assert result.equity_curve == pytest.approx([100000, 100000, 80000, 90000, 90000])
    assert result.max_drawdown == pytest.approx(0.2)
    assert result.total_return == pytest.approx(-0.1)


def test_pre_gap_gex_does_not_reappear_on_later_contiguous_bars():
    timestamps = [f"2025-01-15 09:{minute}" for minute in [30, 31, 33, 34, 35, 36]]
    prices, gex = frames([100] * 6, [0, -2e9, 0, 0, 0, 0], timestamps)
    result = VectorBTBacktester.run_gex_signal_backtest(prices, gex.iloc[:2], fees=0, slippage=0)
    assert result.total_trades == 0


def test_fresh_gex_after_a_gap_signals_only_after_it_is_observed():
    timestamps = [f"2025-01-15 09:{minute}" for minute in [30, 31, 33, 34, 35, 36, 37]]
    prices, gex = frames([100, 100, 25, 50, 200, 100, 120], [0, -2e9, 0, 0, -2e9, 0, 0], timestamps)
    result = VectorBTBacktester.run_gex_signal_backtest(
        prices, gex.iloc[[0, 1, 4]], fees=0, slippage=0
    )
    assert result.open_trades == 1
    assert result.total_return == pytest.approx(0.2)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fees": -0.01},
        {"slippage": 1},
        {"initial_cash": 0},
        {"position_size": 0},
        {"position_size": 1.1},
        {"execution_delay_bars": 0},
        {"execution_delay_bars": 1.5},
        {"entry_threshold": np.nan},
        {"entry_threshold": 1e9, "exit_threshold": 0},
    ],
)
def test_rejects_invalid_execution_parameters(kwargs):
    price_data, gex_data = frames([100] * 3, [-2e9] * 3)
    with pytest.raises(ValueError):
        VectorBTBacktester.run_gex_signal_backtest(price_data, gex_data, **kwargs)


def test_rejects_mismatched_naive_and_aware_timestamps():
    prices, gex = frames([100] * 3, [-2e9] * 3)
    gex.index = gex.index.tz_localize(None)
    with pytest.raises(ValueError):
        VectorBTBacktester.run_gex_signal_backtest(prices, gex)


def test_regime_comparison_attributes_returns_to_the_preceding_signal():
    price_data, gex_data = frames([100, 110, 99, 108.9], [-2e9, 2e9, -2e9, 2e9])
    result = VectorBTBacktester.run_regime_comparison(price_data, gex_data)
    assert result["short_gamma"]["count"] == 2
    assert result["short_gamma"]["mean_return"] == pytest.approx(0.1)
    assert result["short_gamma"]["total_return"] == pytest.approx(0.21)
    assert result["long_gamma"]["count"] == 1
    assert result["long_gamma"]["mean_return"] == pytest.approx(-0.1)


def test_regime_comparison_excludes_returns_across_missing_bars():
    timestamps = [f"2025-01-15 09:{minute}" for minute in [30, 31, 33, 34, 35]]
    prices, gex = frames([100, 110, 220, 242, 242], [-2e9, 2e9, -2e9, 2e9, 2e9], timestamps)
    result = VectorBTBacktester.run_regime_comparison(prices, gex)
    assert result["short_gamma"]["count"] == 2
    assert result["short_gamma"]["total_return"] == pytest.approx(0.21)
    assert result["long_gamma"]["count"] == 1
    assert result["long_gamma"]["total_return"] == 0


@pytest.mark.parametrize("legacy", [False, True])
def test_regime_returns_exclude_overnight_gaps(legacy):
    timestamps = ["2025-01-15 15:50", "2025-01-15 15:55", "2025-01-16 09:30", "2025-01-16 09:35"]
    price_data, gex_data = frames([100, 110, 220, 198], [-2e9, 2e9, -2e9, 2e9], timestamps)
    if legacy:
        result = TradingStrategy.regime_based_strategy(gex_data, price_data)
        assert result["long_gamma"]["count"] == 0
    else:
        result = VectorBTBacktester.run_regime_comparison(price_data, gex_data)
        assert result["long_gamma"]["count"] == 0
        assert result["short_gamma"]["mean_return"] == pytest.approx(0)


@pytest.mark.parametrize("column,values", [("close", [100, 0, 100]), ("net_gex", [0, np.nan, 0])])
def test_regime_comparison_rejects_invalid_observations(column, values):
    price_data, gex_data = frames([100] * 3, [0] * 3)
    if column == "close":
        price_data[column] = values
    else:
        gex_data[column] = values
    with pytest.raises(ValueError):
        VectorBTBacktester.run_regime_comparison(price_data, gex_data)


def test_equity_downsampling_retains_the_end_and_matches_timestamps():
    # Buy at100, final bar is a loss which must remain visible in the chart.
    result = run([100] * 1000 + [90], [-2e9] * 1001)
    assert len(result.equity_curve) <= 500
    assert result.equity_curve[-1] == pytest.approx(90000)
    assert len(result.equity_timestamps) == len(result.equity_curve)
    assert result.equity_timestamps[-1] == result.end_date
