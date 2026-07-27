"""Electrode / ADC front-end model.

Takes a clean spike train (times + amplitudes) and produces a realistic
electrophysiology waveform: the spikes are convolved with an action-potential-
like kernel, then corrupted by

  - 1/f background noise (the electrode/thermal floor),
  - 50 Hz mains hum + harmonics,
  - slow DC drift (electrode polarisation),
  - occasional motion artifact (a step-like baseline jump).

The result is a sampled ADC trace that looks like real electrophysiology, not
clean synthetics (ARCHITECTURE.md §3, Sprint 1.1 'Done when').

Noise parameters are standard instrumentation values; cited in
`docs/sources.md`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sim.hawkes import Spike

DEFAULT_SAMPLE_RATE: float = 1000.0  # Hz — ADS1115-class, conservative
DEFAULT_MAINS_FREQ: float = 50.0  # Hz — UK/EU mains
DEFAULT_MAINS_AMP: float = 0.05  # mV — typical coupled hum
DEFAULT_DRIFT_AMP: float = 0.5  # mV peak-to-peak over the run
DEFAULT_NOISE_FLOOR: float = 0.02  # mV RMS — 1/f floor
DEFAULT_MOTION_AMP: float = 1.0  # mV — step on motion artifact
DEFAULT_MOTION_RATE: float = 0.001  # Hz — rare events


@dataclass(frozen=True, slots=True)
class ElectrodeConfig:
    """Configuration for the electrode/ADC front-end model.

    Parameters are standard instrumentation values; see `docs/sources.md`.
    """

    sample_rate: float = DEFAULT_SAMPLE_RATE
    mains_freq: float = DEFAULT_MAINS_FREQ
    mains_amp: float = DEFAULT_MAINS_AMP
    drift_amp: float = DEFAULT_DRIFT_AMP
    noise_floor: float = DEFAULT_NOISE_FLOOR
    motion_amp: float = DEFAULT_MOTION_AMP
    motion_rate: float = DEFAULT_MOTION_RATE
    seed: int = 0

    def __post_init__(self) -> None:
        if self.sample_rate <= 0.0:
            raise ValueError("sample_rate must be positive")
        if self.mains_amp < 0.0:
            raise ValueError("mains_amp must be non-negative")
        if self.noise_floor < 0.0:
            raise ValueError("noise_floor must be non-negative")
        if self.motion_rate < 0.0:
            raise ValueError("motion_rate must be non-negative")


def _spike_kernel(sample_rate: float) -> np.ndarray:
    """A biphasic action-potential-like kernel (~5 ms wide).

    Modelled as a fast positive Gaussian followed by a slower negative
    Gaussian offset in time — the classic extracellular spike shape
    (positive peak, then negative undershoot).
    """
    width_ms = 5.0
    n = int(width_ms * 1e-3 * sample_rate)
    t = np.arange(-n, n + 1) / sample_rate * 1e3  # ms
    # Positive peak at t=0 (narrow), negative undershoot offset to +1.0 ms (wider).
    pos = np.exp(-((t / 0.6) ** 2))
    neg = 0.4 * np.exp(-(((t - 1.0) / 1.4) ** 2))
    kernel = pos - neg
    kernel /= np.max(np.abs(kernel))  # normalise to unit peak
    return kernel


def _one_over_f_noise(n: int, rng: np.random.Generator, floor: float) -> np.ndarray:
    """Generate 1/f noise by filtering white noise with a 1/sqrt(f) spectrum."""
    # White noise, then shape its spectrum.
    white = rng.standard_normal(n)
    spec = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, d=1.0)
    # Avoid div-by-zero at DC; shape as 1/sqrt(f) for f > 0, keep DC at 0.
    shape = np.ones_like(freqs)
    nonzero = freqs > 0
    shape[nonzero] = 1.0 / np.sqrt(freqs[nonzero])
    spec *= shape
    noise = np.fft.irfft(spec, n=n)
    # Normalise to the requested RMS floor.
    rms = np.sqrt(np.mean(noise**2))
    if rms > 0:
        noise = noise * (floor / rms)
    return noise


def render_channel(
    spikes: list[Spike],
    duration: float,
    config: ElectrodeConfig | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Render a single electrode channel as a sampled ADC trace.

    Returns `(times, voltage)` where `times` is the sample timestamps in
    seconds and `voltage` is the trace in mV.
    """
    cfg = config or ElectrodeConfig()
    rng = np.random.default_rng(cfg.seed)
    fs = cfg.sample_rate
    n = int(duration * fs)
    t = np.arange(n) / fs

    # 1. Spike signal: convolve each spike's amplitude with the AP kernel.
    signal = np.zeros(n)
    kernel = _spike_kernel(fs)
    half = len(kernel) // 2
    for s in spikes:
        idx = int(s.time * fs)
        if 0 <= idx < n:
            lo = idx - half
            hi = idx + half + 1
            k_lo = max(0, -lo)
            k_hi = len(kernel) - max(0, hi - n)
            sig_lo = max(0, lo)
            sig_hi = min(n, hi)
            if sig_hi > sig_lo and k_hi > k_lo:
                signal[sig_lo:sig_hi] += s.amplitude * kernel[k_lo:k_hi]

    # 2. 1/f background noise.
    noise = _one_over_f_noise(n, rng, cfg.noise_floor)

    # 3. 50 Hz mains hum + 3rd harmonic.
    hum = cfg.mains_amp * (
        np.sin(2 * np.pi * cfg.mains_freq * t) + 0.3 * np.sin(2 * np.pi * 3 * cfg.mains_freq * t)
    )

    # 4. Slow DC drift: a low-frequency sinusoid plus a random walk.
    drift = 0.5 * cfg.drift_amp * np.sin(2 * np.pi * 0.0005 * t - np.pi / 2)
    # Random-walk component (Brownian), scaled to drift_amp p-p.
    steps = rng.standard_normal(n)
    walk = np.cumsum(steps)
    walk -= walk[0]
    if np.max(np.abs(walk)) > 0:
        walk = walk / np.max(np.abs(walk)) * 0.5 * cfg.drift_amp
    drift += walk

    # 5. Motion artifacts: rare step-like baseline jumps, exponentially
    # decaying back to baseline.
    motion = np.zeros(n)
    if cfg.motion_rate > 0.0:
        expected = cfg.motion_rate * duration
        n_artifacts = rng.poisson(expected)
        for _ in range(n_artifacts):
            onset = rng.integers(0, n)
            amp = rng.normal(0.0, cfg.motion_amp)
            decay = np.exp(-(t - t[onset]) / 0.2)  # 200 ms decay
            decay[:onset] = 0.0
            motion += amp * decay

    voltage = signal + noise + hum + drift + motion
    return t, voltage
