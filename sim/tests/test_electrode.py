"""Tests for the electrode/ADC front-end model.

Sprint 1.1's 'Done when': waveforms look like real electrophysiology, not
clean synthetics. The tests check that each corruption mode is present and
that the spike signal survives on top of the noise floor.
"""

from __future__ import annotations

import numpy as np

from sim.electrode import (
    ElectrodeConfig,
    _one_over_f_noise,
    _spike_kernel,
    render_channel,
)
from sim.hawkes import Spike


def _clean_spikes() -> list[Spike]:
    return [Spike(time=0.5, amplitude=2.0), Spike(time=1.5, amplitude=3.0)]


def test_render_returns_correct_length() -> None:
    cfg = ElectrodeConfig(sample_rate=1000.0, seed=0)
    t, v = render_channel(_clean_spikes(), duration=2.0, config=cfg)
    assert t.shape == (2000,)
    assert v.shape == (2000,)
    assert t[0] == 0.0
    assert abs(t[-1] - 1.999) < 1e-9


def test_spike_kernel_is_biphasic() -> None:
    k = _spike_kernel(1000.0)
    # Positive peak first, negative undershoot after.
    peak_idx = int(np.argmax(k))
    trough_idx = int(np.argmin(k))
    assert peak_idx < trough_idx, "kernel should be positive-then-negative"
    assert k[peak_idx] > 0.0
    assert k[trough_idx] < 0.0
    # Normalised to unit peak.
    assert abs(np.max(np.abs(k)) - 1.0) < 1e-9


def test_one_over_f_has_pink_spectrum() -> None:
    """1/f noise power spectral density should fall off as ~1/f."""
    rng = np.random.default_rng(42)
    noise = _one_over_f_noise(8192, rng, floor=1.0)
    spec = np.abs(np.fft.rfft(noise)) ** 2
    freqs = np.fft.rfftfreq(noise.size, d=1.0)
    # Compare low-band and high-band mean power.
    low = spec[(freqs > 0.01) & (freqs < 0.05)].mean()
    high = spec[(freqs > 0.2) & (freqs < 0.4)].mean()
    assert low > high, f"1/f noise should have more low-freq power: {low} vs {high}"


def test_mains_hum_present_at_50hz() -> None:
    """A quiet trace (no spikes, no drift) still shows a 50 Hz peak."""
    cfg = ElectrodeConfig(
        sample_rate=1000.0,
        mains_amp=0.1,
        noise_floor=0.0,
        drift_amp=0.0,
        motion_amp=0.0,
        motion_rate=0.0,
        seed=0,
    )
    _, v = render_channel([], duration=4.0, config=cfg)
    spec = np.abs(np.fft.rfft(v - v.mean()))
    freqs = np.fft.rfftfreq(v.size, d=1.0 / cfg.sample_rate)
    # Power at 50 Hz should be much greater than the median power.
    idx_50 = int(np.argmin(np.abs(freqs - 50.0)))
    median_power = np.median(spec[1:])  # skip DC
    assert spec[idx_50] > 10 * median_power, (
        f"50 Hz power {spec[idx_50]} not dominant vs median {median_power}"
    )


def test_dc_drift_present() -> None:
    """A trace with drift but no spikes/noise/hum has a slow trend."""
    cfg = ElectrodeConfig(
        sample_rate=1000.0,
        mains_amp=0.0,
        noise_floor=0.0,
        drift_amp=1.0,
        motion_amp=0.0,
        motion_rate=0.0,
        seed=0,
    )
    _, v = render_channel([], duration=60.0, config=cfg)
    # The drift should produce a range wider than the tiny residual noise.
    assert v.max() - v.min() > 0.1, f"drift range {v.max() - v.min()} too small"


def test_spike_signal_survives_above_noise() -> None:
    """With realistic noise, a spike should still produce a detectable peak."""
    cfg = ElectrodeConfig(
        sample_rate=1000.0,
        mains_amp=0.02,
        noise_floor=0.02,
        drift_amp=0.1,
        motion_amp=0.0,
        motion_rate=0.0,
        seed=0,
    )
    spikes = [Spike(time=1.0, amplitude=3.0)]
    _, v = render_channel(spikes, duration=2.0, config=cfg)
    # Peak near t=1.0 should exceed the baseline RMS by a clear margin.
    idx_peak = int(1.0 * cfg.sample_rate)
    window = v[idx_peak - 5 : idx_peak + 6]
    baseline = np.concatenate([v[:500], v[1500:]])
    baseline_rms = np.sqrt(np.mean(baseline**2))
    assert window.max() > 5 * baseline_rms, (
        f"spike peak {window.max()} not clearly above baseline RMS {baseline_rms}"
    )


def test_motion_artifact_produces_step() -> None:
    """A motion artifact produces a sudden baseline jump that decays."""
    cfg = ElectrodeConfig(
        sample_rate=1000.0,
        mains_amp=0.0,
        noise_floor=0.0,
        drift_amp=0.0,
        motion_amp=2.0,
        motion_rate=10.0,  # high rate so we get at least one in 1 s
        seed=42,
    )
    _, v = render_channel([], duration=1.0, config=cfg)
    # There should be a visible step somewhere: max-min range exceeds 0.
    assert v.max() - v.min() > 0.5, "no visible motion artifact step"


def test_reproducible_with_seed() -> None:
    cfg = ElectrodeConfig(seed=99)
    _, v1 = render_channel(_clean_spikes(), duration=2.0, config=cfg)
    _, v2 = render_channel(_clean_spikes(), duration=2.0, config=cfg)
    assert np.array_equal(v1, v2)


def test_invalid_config_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        ElectrodeConfig(sample_rate=0.0)
    with pytest.raises(ValueError):
        ElectrodeConfig(noise_floor=-1.0)
