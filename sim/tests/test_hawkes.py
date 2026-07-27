"""Tests for the Hawkes spike model.

Sprint 0.6's 'Done when': generated ISI matches published statistics within
tolerance. The headline test checks that the empirical mean ISI is consistent
with the theoretical rate for a stationary Hawkes process, and that the
process is visibly burstier than a Poisson process with the same mean rate.
"""

from __future__ import annotations

import numpy as np

from sim.hawkes import (
    HawkesConfig,
    HawkesProcess,
    simulate_electrode,
)


def test_branching_ratio_enforced_below_one() -> None:
    import pytest

    with pytest.raises(ValueError, match="branching ratio"):
        HawkesConfig(alpha=0.2, beta=0.1)  # η = 2.0


def test_simulate_produces_events() -> None:
    proc = HawkesProcess(HawkesConfig(seed=42))
    proc.simulate(duration=1000.0)
    assert len(proc.events) > 0
    assert proc.times[0] >= 0.0
    assert proc.times[-1] < 1000.0


def test_zero_duration_rejected() -> None:
    import pytest

    proc = HawkesProcess(HawkesConfig(seed=1))
    with pytest.raises(ValueError):
        proc.simulate(0.0)


def test_mean_isi_matches_theoretical_rate() -> None:
    """Empirical mean ISI ≈ 1 / theoretical_mean_rate, within tolerance."""
    cfg = HawkesConfig(baseline_rate=0.05, alpha=0.04, beta=0.1, seed=7)
    proc = HawkesProcess(cfg)
    # Long run so the law of large numbers applies.
    proc.simulate(duration=200_000.0)
    isis = proc.inter_spike_intervals()
    assert len(isis) > 1000, f"too few events: {len(isis)}"

    empirical_mean_isi = float(isis.mean())
    theoretical_mean_isi = 1.0 / cfg.theoretical_mean_rate
    rel_err = abs(empirical_mean_isi - theoretical_mean_isi) / theoretical_mean_isi
    assert rel_err < 0.05, (
        f"mean ISI {empirical_mean_isi:.4f}s vs theoretical "
        f"{theoretical_mean_isi:.4f}s (rel err {rel_err:.3f})"
    )


def test_hawkes_is_burstier_than_poisson() -> None:
    """A Hawkes process has a higher coefficient of variation of ISI than a
    Poisson process (which has CV = 1). Self-excitation produces burstiness."""
    cfg = HawkesConfig(baseline_rate=0.05, alpha=0.05, beta=0.1, seed=11)
    proc = HawkesProcess(cfg)
    proc.simulate(duration=50_000.0)
    isis = proc.inter_spike_intervals()
    cv = float(isis.std() / isis.mean())
    # A Poisson process has CV = 1.0 exactly. A Hawkes process with η > 0
    # has CV > 1. We allow a margin for finite-sample noise.
    assert cv > 1.1, (
        f"Hawkes CV {cv:.3f} not visibly above Poisson CV=1.0; "
        "self-excitation not producing burstiness"
    )


def test_amplitudes_are_distributed() -> None:
    cfg = HawkesConfig(amplitude_mean=3.0, amplitude_std=0.5, seed=3)
    proc = HawkesProcess(cfg)
    proc.simulate(duration=5000.0)
    amps = proc.amplitudes
    assert amps.size > 0
    # Mean amplitude should be close to the configured mean.
    assert abs(float(amps.mean()) - 3.0) < 0.5


def test_per_channel_seed_is_deterministic() -> None:
    """Two runs with the same channel and config produce identical spikes."""
    a = simulate_electrode(HawkesConfig(seed=100), duration=2000.0, channel=5)
    b = simulate_electrode(HawkesConfig(seed=100), duration=2000.0, channel=5)
    assert np.array_equal(a.times, b.times)
    assert np.array_equal(a.amplitudes, b.amplitudes)


def test_different_channels_produce_different_trains() -> None:
    a = simulate_electrode(HawkesConfig(seed=100), duration=2000.0, channel=0)
    b = simulate_electrode(HawkesConfig(seed=100), duration=2000.0, channel=1)
    assert not np.array_equal(a.times, b.times)


def test_theoretical_mean_rate_formula() -> None:
    """Theoretical mean rate = μ / (1 - η) where η = α/β."""
    cfg = HawkesConfig(baseline_rate=0.02, alpha=0.04, beta=0.1)
    expected = 0.02 / (1.0 - 0.04 / 0.1)
    assert abs(cfg.theoretical_mean_rate - expected) < 1e-12
