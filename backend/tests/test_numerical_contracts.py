"""Counterexamples for repriced roots and dollar delta-hedge scenarios."""

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from app.core.charm_vanna_calculator import CharmVannaCalculator
from app.core.gex_calculator import GEXCalculator

ET = ZoneInfo("America/New_York")
NOW = datetime(2024, 1, 15, 12, tzinfo=ET)
YEAR_MINUTES = 365.25 * 24 * 60


def chain(rows, years=0.1):
    expiration = NOW + timedelta(minutes=years * YEAR_MINUTES)
    return pd.DataFrame(
        [
            {
                "strike": strike,
                "type": option_type,
                "open_interest": oi,
                "implied_vol": iv,
                "expiration": expiration,
            }
            for strike, option_type, oi, iv in rows
        ]
    )


def test_zero_gamma_reprices_spot_instead_of_summing_strikes():
    # Equal OI/IV/T gives d1_put=-d1_call at sqrt(95*105)*exp(-sigma²*T/2).
    snapshot = GEXCalculator(risk_free_rate=0, dividend_yield=0).calculate_gex_from_chain(
        chain([(95, "put", 100, 0.2), (105, "call", 100, 0.2)]), 100, NOW
    )
    assert snapshot.zero_gamma_level == pytest.approx(99.67537155038006, abs=1e-7)
    assert snapshot.metrics["zero_gamma_crossing_found"] is True
    assert snapshot.metrics["zero_gamma_relation"] == "in_range"


def test_zero_gamma_accepts_a_crossing_at_the_search_boundary():
    root = 99.67537155038006
    snapshot = GEXCalculator(risk_free_rate=0, dividend_yield=0).calculate_gex_from_chain(
        chain([(95, "put", 100, 0.2), (105, "call", 100, 0.2)]), root / 0.8, NOW
    )
    assert snapshot.zero_gamma_level == pytest.approx(root, abs=1e-7)
    assert snapshot.metrics["zero_gamma_crossing_found"] is True


@pytest.mark.parametrize("spot, expected", [(100, 95.14762019654191), (106, 105.09984358351241)])
def test_zero_gamma_keeps_each_contract_iv_and_selects_nearest_root(spot, expected):
    # At K=100, equal OI but IV=.1/.3 yields two roots of gamma_call=gamma_put.
    snapshot = GEXCalculator(risk_free_rate=0, dividend_yield=0).calculate_gex_from_chain(
        chain([(100, "call", 100, 0.1), (100, "put", 100, 0.3)]), spot, NOW
    )
    assert snapshot.zero_gamma_level == pytest.approx(expected, abs=1e-7)
    assert snapshot.metrics["zero_gamma_crossing_found"] is True


def test_zero_gamma_resolves_multiple_near_expiry_crossings_between_contract_centers():
    # Narrow/medium/wide kernels have four roots despite all centers and coarse
    # grid points being positive; the nearest is below spot by .0016379 points.
    snapshot = GEXCalculator(risk_free_rate=0, dividend_yield=0).calculate_gex_from_chain(
        chain(
            [(100, "call", 2, 0.01), (100, "call", 20, 0.2), (100, "put", 20, 0.1)],
            1 / YEAR_MINUTES,
        ),
        100,
        NOW,
    )
    assert snapshot.zero_gamma_level == pytest.approx(99.99836208880899, abs=1e-7)
    assert snapshot.metrics["zero_gamma_crossing_found"] is True


@pytest.mark.parametrize("years", [0.1, 1 / YEAR_MINUTES, 0, -0.1])
def test_one_sided_or_expired_chain_does_not_claim_a_root(years):
    snapshot = GEXCalculator(risk_free_rate=0, dividend_yield=0).calculate_gex_from_chain(
        chain([(80, "put", 100, 0.2), (90, "put", 200, 0.2)], years), 100, NOW
    )
    assert snapshot.zero_gamma_level == 100
    assert snapshot.metrics["zero_gamma_crossing_found"] is False
    assert "zero_gamma_relation" not in snapshot.metrics


def test_identically_cancelled_chain_does_not_claim_a_regime_crossing():
    snapshot = GEXCalculator(risk_free_rate=0, dividend_yield=0).calculate_gex_from_chain(
        chain([(100, "call", 100, 0.2), (100, "put", 100, 0.2)]), 100, NOW
    )
    assert snapshot.net_gex == 0
    assert snapshot.metrics["zero_gamma_crossing_found"] is False


@pytest.mark.parametrize(
    "invalid",
    [
        (-1, "put", 100, 0.2),
        (0, "put", 100, 0.2),
        (math.inf, "put", 100, 0.2),
        (90, "put", math.inf, 0.2),
        (90, "unknown", 100, 0.2),
    ],
)
def test_invalid_strike_inventory_or_type_cannot_contaminate_numeric_outputs(invalid):
    snapshot = GEXCalculator(risk_free_rate=0, dividend_yield=0).calculate_gex_from_chain(
        chain([(100, "call", 100, 0.2), invalid]), 100, NOW
    )
    assert list(snapshot.gex_by_strike) == [100.0]
    assert snapshot.total_put_gex == 0
    assert math.isfinite(snapshot.net_gex)
    assert snapshot.metrics["zero_gamma_crossing_found"] is False


@pytest.mark.parametrize("option_type, sign", [("call", 1), ("put", -1)])
def test_charm_scenario_is_dollar_hedge_change(option_type, sign):
    calculator = CharmVannaCalculator(risk_free_rate=0, dividend_yield=0)
    result, by_strike = calculator.calculate_charm_flow(
        np.array([100.0]),
        np.array([option_type]),
        np.array([1.0]),
        np.array([0.2]),
        np.array([0.01]),
        100,
    )
    # Delta=Phi(sigma*sqrt(T)/2); subtract the 30-minute later delta,
    # reverse the inventory sign and multiply by 100 contracts * $100 spot.
    assert result == pytest.approx(sign * 0.11393248567470593, abs=1e-9)
    assert by_strike[100] == result


@pytest.mark.parametrize(
    "option_type, expected",
    [
        ("call", -4541.786259432539),
        ("put", 4541.786259432539),
    ],
)
def test_charm_stops_at_expiry_instead_of_extrapolating_thirty_minutes(option_type, expected):
    calculator = CharmVannaCalculator(risk_free_rate=0, dividend_yield=0)
    result, _ = calculator.calculate_charm_flow(
        np.array([99.99]),
        np.array([option_type]),
        np.array([1.0]),
        np.array([0.2]),
        np.array([10 / YEAR_MINUTES]),
        100,
    )
    assert result == pytest.approx(expected, abs=1e-7)


@pytest.mark.parametrize("option_type, sign", [("call", 1), ("put", -1)])
def test_vanna_scenario_is_exact_dollar_hedge_change(option_type, sign):
    calculator = CharmVannaCalculator(risk_free_rate=0, dividend_yield=0)
    result, _ = calculator.calculate_vanna_flow(
        np.array([100.0]),
        np.array([option_type]),
        np.array([1.0]),
        np.array([0.2]),
        np.array([0.01]),
        100,
    )
    # Phi(.0095)-Phi(.01), from an absolute IV bump .20 -> .19.
    assert result == pytest.approx(sign * 1.994616572358332, abs=1e-9)


def test_expired_contracts_produce_no_future_delta_flow():
    calculator = CharmVannaCalculator()
    data = chain([(99, "call", 100, 0.2), (101, "put", 100, 0.2)])
    result = calculator.calculate_all(data, 100, np.array([0.0, -0.1]))
    assert result["charm_flow"] == 0
    assert result["vanna_flow"] == 0


def test_iv_scenario_at_the_supported_floor_cannot_make_volatility_negative():
    calculator = CharmVannaCalculator(risk_free_rate=0, dividend_yield=0)
    result, _ = calculator.calculate_vanna_flow(
        np.array([100.0]),
        np.array(["call"]),
        np.array([1.0]),
        np.array([0.01]),
        np.array([0.01]),
        100,
    )
    assert result == 0


def test_near_expiry_gamma_matches_delta_finite_difference():
    snapshot = GEXCalculator(risk_free_rate=0, dividend_yield=0).calculate_gex_from_chain(
        chain([(100, "call", 1, 0.2)], 5 / YEAR_MINUTES), 100, NOW
    )
    time_years = 5 / YEAR_MINUTES

    def delta(spot):
        d1 = (math.log(spot / 100) + 0.5 * 0.2**2 * time_years) / (0.2 * math.sqrt(time_years))
        return 0.5 * (1 + math.erf(d1 / math.sqrt(2)))

    gamma = (delta(100.00001) - delta(99.99999)) / 0.00002
    assert snapshot.net_gex == pytest.approx(gamma * 100 * 100**2 * 0.01, rel=1e-7)


def test_small_charm_scenario_matches_near_expiry_delta_derivative():
    time_years = 5 / YEAR_MINUTES
    log_moneyness = math.log(100 / 100.01)
    d1 = (log_moneyness + 0.5 * 0.2**2 * time_years) / (0.2 * math.sqrt(time_years))
    density = math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi)
    delta_time_derivative = density * (
        0.2 / (4 * math.sqrt(time_years)) - log_moneyness / (2 * 0.2 * time_years**1.5)
    )
    minutes = 0.001
    calculator = CharmVannaCalculator(
        risk_free_rate=0, dividend_yield=0, time_advance_minutes=minutes
    )
    result, _ = calculator.calculate_charm_flow(
        np.array([100.01]),
        np.array(["call"]),
        np.array([1.0]),
        np.array([0.2]),
        np.array([time_years]),
        100,
    )
    # Calendar time lowers T; reversing call inventory change reverses it again.
    assert result / (minutes / YEAR_MINUTES) == pytest.approx(
        delta_time_derivative * 100 * 100, rel=0.0002
    )


def test_small_vanna_scenario_matches_near_expiry_delta_derivative():
    time_years = 5 / YEAR_MINUTES
    d1 = (math.log(100 / 100.01) + 0.5 * 0.2**2 * time_years) / (0.2 * math.sqrt(time_years))
    density = math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi)
    delta_iv_derivative = density * (
        -math.log(100 / 100.01) / (0.2**2 * math.sqrt(time_years)) + 0.5 * math.sqrt(time_years)
    )
    calculator = CharmVannaCalculator(risk_free_rate=0, dividend_yield=0, iv_bump=-0.000001)
    result, _ = calculator.calculate_vanna_flow(
        np.array([100.01]),
        np.array(["call"]),
        np.array([1.0]),
        np.array([0.2]),
        np.array([time_years]),
        100,
    )
    assert result / -0.000001 == pytest.approx(-delta_iv_derivative * 100 * 100, rel=1e-5)


@pytest.mark.parametrize("calculator", [GEXCalculator(), CharmVannaCalculator()])
def test_strike_aggregation_preserves_signed_values_and_sorted_keys(calculator):
    result = calculator._aggregate_by_strike(
        np.array([2.0, 1.0, 2.0, 3.0, 1.0]), np.array([1_000_000_000.0, -4.0, 3.0, -2.0, 6.0])
    )
    assert list(result) == [1.0, 2.0, 3.0]
    assert result == {1.0: 2.0, 2.0: 1_000_000_003.0, 3.0: -2.0}


def test_hidden_flow_uses_the_same_dynamic_rate_as_gex():
    class RateProvider:
        def get_rate(self):
            return 0.12

    data = chain([(100, "call", 100, 0.2)])
    dynamic = GEXCalculator(risk_free_rate=0.01, dividend_yield=0, rate_provider=RateProvider())
    static = GEXCalculator(risk_free_rate=0.12, dividend_yield=0)
    dynamic_result = dynamic.calculate_gex_from_chain(data, 100, NOW)
    static_result = static.calculate_gex_from_chain(data, 100, NOW)
    assert (
        dynamic_result.advanced_analytics.charm_vanna
        == static_result.advanced_analytics.charm_vanna
    )
