"""Scalar-reference checks for bounded, vectorized zero-gamma sampling."""

import math

import numpy as np
import pytest
from scipy.optimize import brentq

from app.core.gex_calculator import GEXCalculator


def scalar_zero_gamma(strikes, types, interest, iv, expiry, spot, rate=0.0, dividend=0.0):
    """Prior scalar scan, independently retaining the same candidate/root contract."""
    active = expiry > 0
    kernels, inverse = np.unique(
        np.column_stack((strikes[active], iv[active], expiry[active])),
        axis=0,
        return_inverse=True,
    )
    inventory = np.bincount(
        inverse, weights=np.where(types[active] == "call", 1.0, -1.0) * interest[active]
    )
    kernels, inventory = kernels[inventory != 0], inventory[inventory != 0]
    if not inventory.size or np.all(np.sign(inventory) == np.sign(inventory[0])):
        return spot, False, None
    strikes, iv, expiry = kernels.T
    expiry = np.maximum(expiry, 1e-10)
    width = iv * np.sqrt(expiry)
    centers = np.log(strikes) - (rate - dividend + 0.5 * iv**2) * expiry
    weights = np.log(np.abs(inventory)) - dividend * expiry - np.log(width)

    def evaluate(candidate):
        log_gamma = weights - 0.5 * ((math.log(candidate) - centers) / width) ** 2
        gamma = np.exp(log_gamma - np.max(log_gamma))
        return float(np.dot(np.sign(inventory), gamma) / np.sum(gamma))

    lower, upper = spot * 0.8, spot * 1.2
    flanks = np.exp(centers[:, None] + width[:, None] * [-1, 0, 1]).ravel()
    points = np.unique(
        np.concatenate(
            (
                np.geomspace(lower, upper, 257),
                [spot],
                strikes[(strikes >= lower) & (strikes <= upper)],
                flanks[(flanks >= lower) & (flanks <= upper)],
            )
        )
    )
    values = np.array([evaluate(point) for point in points])
    tolerance = 64 * np.finfo(float).eps
    nonzero = np.flatnonzero(np.abs(values) > tolerance)
    roots = []
    for boundary, value in ((lower, values[0]), (upper, values[-1])):
        if nonzero.size and abs(value) <= tolerance:
            step = boundary * np.sqrt(np.finfo(float).eps)
            if evaluate(boundary - step) * evaluate(boundary + step) < 0:
                root = brentq(evaluate, boundary - step, boundary + step, xtol=1e-9)
                if lower - 1e-9 <= root <= upper + 1e-9:
                    roots.append(float(np.clip(root, lower, upper)))
    for left, right in zip(nonzero[:-1], nonzero[1:], strict=True):
        if np.signbit(values[left]) != np.signbit(values[right]):
            roots.append(brentq(evaluate, points[left], points[right], xtol=1e-9))
    if not roots:
        return spot, False, None
    return min(roots, key=lambda root: (abs(root - spot), root)), True, "in_range"


def mixed_expiry_inputs(n=258):
    index = np.arange(n)
    return (
        np.resize(np.arange(6200.0, 7005.0, 5.0), n),
        np.where(index % 2, "put", "call"),
        (100 + (index * 137) % 5000).astype(float),
        0.12 + index * 0.00013,
        np.resize(np.array([4 / 24, 1, 7, 30, 60]) / 365.25, n),
        6600.0,
    )


@pytest.mark.parametrize(
    "rows, spot",
    [
        ([(95, "put", 100, 0.2, 0.1), (105, "call", 100, 0.2, 0.1)], 100),
        ([(100, "put", 100, 0.2, 0.1), (100, "call", 100, 0.2, 0.1)], 100),
        ([(95, "put", 100, 0.2, 0.1), (105, "put", 100, 0.3, 0.01)], 100),
        ([(100, "call", 1000000, 0.2, 0.1), (100, "put", 1, 0.21, 0.1)], 100),
        (
            [
                (100 * math.exp(0.5 * 0.2**2 * 0.1), "call", 100, 0.2, 0.1),
                (100 * math.exp(0.5 * 0.4**2 * 0.1), "put", 200, 0.4, 0.1),
            ],
            100,
        ),
        ([(100, "call", 100, 0.1, 0.1), (100, "put", 100, 0.3, 0.1)], 106),
        ([(95, "put", 100, 0.2, 0.1), (105, "call", 100, 0.2, 0.1)], 99.67537155038006 / 0.8),
        ([(95, "put", 100, 0.2, 0.1), (105, "call", 100, 0.2, 0.1)], 99.67537155038006 / 1.2),
        ([(95, "put", 100, 0.2, 0.1), (105, "call", 100, 0.2, 0.1)], 99.67537155038006),
        (
            [
                (100, "call", 2, 0.01, 1 / 525960),
                (100, "call", 20, 0.2, 1 / 525960),
                (100, "put", 20, 0.1, 1 / 525960),
            ],
            100,
        ),
    ],
)
def test_scalar_reference_preserves_crossings_and_cancellation(rows, spot):
    strikes, types, interest, iv, expiry = zip(*rows, strict=True)
    inputs = (
        np.array(strikes),
        np.array(types),
        np.array(interest),
        np.array(iv),
        np.array(expiry),
        spot,
    )
    expected = scalar_zero_gamma(*inputs)
    actual = GEXCalculator(risk_free_rate=0, dividend_yield=0)._find_zero_gamma_level(*inputs, 0)
    assert actual[1:] == expected[1:]
    assert actual[0] == pytest.approx(expected[0], abs=1e-7)


@pytest.mark.parametrize("n", [257, 258, 513])
def test_distinct_iv_mixed_expiry_matches_scalar_across_chunk_boundaries(n):
    inputs = mixed_expiry_inputs(n)
    expected = scalar_zero_gamma(*inputs, rate=0.043, dividend=0.013)
    actual = GEXCalculator(risk_free_rate=0.043, dividend_yield=0.013)._find_zero_gamma_level(
        *inputs, 0.043
    )
    assert actual[1:] == expected[1:]
    assert actual[0] == pytest.approx(expected[0], abs=1e-7)


def test_sampling_vectorizes_points_with_bounded_workspace(monkeypatch):
    # Per-point Python evaluation or a full points-by-kernels matrix breaks this bound.
    inputs = mixed_expiry_inputs(1024)
    exp = np.exp
    sampled_shapes = []
    scalar_calls = 0

    def observe_exp(values, *args, **kwargs):
        nonlocal scalar_calls
        if values.ndim == 2 and values.shape[-1] == 1024:
            sampled_shapes.append(values.shape)
        elif values.shape == (1024,):
            scalar_calls += 1
        return exp(values, *args, **kwargs)

    monkeypatch.setattr(np, "exp", observe_exp)
    result = GEXCalculator()._find_zero_gamma_level(*inputs, 0.043)
    assert math.isfinite(result[0])
    assert sampled_shapes, "the scan must evaluate multiple candidate points per NumPy call"
    assert max(math.prod(shape) for shape in sampled_shapes) <= 131072
    assert sum(shape[0] for shape in sampled_shapes) > 1024
    # Scalar evaluations remain for actual root refinement, not every sample point.
    assert scalar_calls < sum(shape[0] for shape in sampled_shapes) / 10
