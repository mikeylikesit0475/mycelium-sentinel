"""Tests for the contaminant -> spike-response coupling (ADR-008).

These tests verify the coupling math, NOT a biological claim. The coupling is
illustrative — flagged in `docs/sources.md`, the README, and the module itself.
"""

from __future__ import annotations

import itertools

import pytest

from sim.coupling import (
    DEFAULT_K_AMP,
    DEFAULT_K_RATE,
    CouplingConfig,
    apply_coupling,
)


def test_zero_concentration_is_baseline() -> None:
    """C=0 should leave the parameters unchanged."""
    out = apply_coupling(
        baseline_rate=0.01, amplitude_mean=3.0, amplitude_std=1.0, concentration=0.0
    )
    assert abs(out.baseline_rate - 0.01) < 1e-9
    assert abs(out.amplitude_mean - 3.0) < 1e-9
    assert abs(out.amplitude_std - 1.0) < 1e-9


def test_positive_concentration_increases_rate() -> None:
    out = apply_coupling(0.01, 3.0, 1.0, concentration=1.0)
    assert out.baseline_rate > 0.01
    # Default k_rate=5: mu_eff = 0.01 * (1 + 5*1) = 0.06.
    assert abs(out.baseline_rate - 0.06) < 1e-9


def test_positive_concentration_increases_amplitude() -> None:
    out = apply_coupling(0.01, 3.0, 1.0, concentration=1.0)
    assert out.amplitude_mean > 3.0
    # Default k_amp=0.5: amp_eff = 3.0 * (1 + 0.5*1) = 4.5.
    assert abs(out.amplitude_mean - 4.5) < 1e-9


def test_rate_scales_linearly_with_concentration() -> None:
    """The coupling is monotonic linear in C (the demo's assumption)."""
    rates = [
        apply_coupling(0.01, 3.0, 1.0, concentration=c).baseline_rate for c in [0.0, 0.5, 1.0, 2.0]
    ]
    for a, b in itertools.pairwise(rates):
        assert b > a, "rate should increase monotonically with concentration"


def test_negative_concentration_rejected() -> None:
    with pytest.raises(ValueError):
        apply_coupling(0.01, 3.0, 1.0, concentration=-1.0)


def test_negative_k_rate_rejected() -> None:
    with pytest.raises(ValueError):
        CouplingConfig(k_rate=-1.0)


def test_custom_config_overrides_defaults() -> None:
    cfg = CouplingConfig(k_rate=10.0, k_amp=1.0)
    out = apply_coupling(0.01, 3.0, 1.0, concentration=1.0, config=cfg)
    # mu_eff = 0.01 * (1 + 10*1) = 0.11; amp_eff = 3.0 * (1 + 1*1) = 6.0.
    assert abs(out.baseline_rate - 0.11) < 1e-9
    assert abs(out.amplitude_mean - 6.0) < 1e-9


def test_default_parameters_are_the_documented_guesses() -> None:
    assert DEFAULT_K_RATE == 5.0
    assert DEFAULT_K_AMP == 0.5


def test_amplitude_std_scales_proportionally() -> None:
    """The amplitude CV should stay roughly constant under coupling."""
    out = apply_coupling(0.01, 3.0, 1.0, concentration=2.0)
    cv = out.amplitude_std / out.amplitude_mean
    baseline_cv = 1.0 / 3.0
    assert abs(cv - baseline_cv) < 1e-9
