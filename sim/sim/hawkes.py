"""Hawkes self-exciting point process for mycelial spike trains.

A Hawkes process has intensity

    λ(t) = μ + Σ_i α · exp(-β · (t - t_i))   for t_i < t

where μ is the baseline rate, α the self-excitation strength, and β the decay
rate of the excitation kernel. The self-excitation is what gives the bursty
clustering seen in real fungal recordings — a plain Poisson process looks
obviously wrong next to them (ARCHITECTURE.md §3).

Simulation uses Ogata's thinning algorithm: propose events from an upper-bound
homogeneous Poisson process and accept/reject against the true intensity.

Parameters are cited in `docs/sources.md` (Adamatzky's fungal electrophysiology
papers). The branching ratio η = α/β is kept below 1 so the process is
stationary.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_BASELINE_RATE: float = 0.01  # Hz — one spike per ~100 s
DEFAULT_ALPHA: float = 0.04  # Hz — self-excitation strength
DEFAULT_BETA: float = 0.1  # Hz — excitation decay
DEFAULT_AMPLITUDE_MEAN: float = 3.0  # mV
DEFAULT_AMPLITUDE_STD: float = 1.0  # mV


@dataclass(frozen=True, slots=True)
class HawkesConfig:
    """Configuration for a Hawkes spike train.

    Parameters are cited in `docs/sources.md`. The branching ratio `η = α/β`
    must be below 1 for stationarity.
    """

    baseline_rate: float = DEFAULT_BASELINE_RATE
    alpha: float = DEFAULT_ALPHA
    beta: float = DEFAULT_BETA
    amplitude_mean: float = DEFAULT_AMPLITUDE_MEAN
    amplitude_std: float = DEFAULT_AMPLITUDE_STD
    seed: int = 0

    def __post_init__(self) -> None:
        if self.baseline_rate < 0.0:
            raise ValueError("baseline_rate must be non-negative")
        if self.alpha < 0.0:
            raise ValueError("alpha must be non-negative")
        if self.beta <= 0.0:
            raise ValueError("beta must be positive")
        if self.branching_ratio >= 1.0:
            raise ValueError(
                f"branching ratio α/β = {self.branching_ratio:.3f} must be < 1 "
                "for a stationary Hawkes process"
            )
        if self.amplitude_std < 0.0:
            raise ValueError("amplitude_std must be non-negative")

    @property
    def branching_ratio(self) -> float:
        """The branching ratio η = α/β. Must be < 1 for stationarity."""
        return self.alpha / self.beta

    @property
    def theoretical_mean_rate(self) -> float:
        """Theoretical long-run mean event rate (Hz).

        For a stationary Hawkes process the mean rate is μ / (1 - η).
        """
        return self.baseline_rate / (1.0 - self.branching_ratio)


@dataclass(frozen=True, slots=True)
class Spike:
    """A single spike event."""

    time: float  # seconds since process start
    amplitude: float  # mV


class HawkesProcess:
    """A univariate Hawkes self-exciting point process.

    Simulate via Ogata's thinning algorithm. Each instance carries its own
    RNG so runs are reproducible from the `seed` in the config.
    """

    def __init__(self, config: HawkesConfig | None = None) -> None:
        self.config = config or HawkesConfig()
        self._rng = np.random.default_rng(self.config.seed)
        self.events: list[Spike] = []

    @property
    def times(self) -> np.ndarray:
        """Array of event times (seconds)."""
        return np.array([e.time for e in self.events], dtype=np.float64)

    @property
    def amplitudes(self) -> np.ndarray:
        """Array of event amplitudes (mV)."""
        return np.array([e.amplitude for e in self.events], dtype=np.float64)

    def _intensity(self, t: float) -> float:
        """Compute λ(t) given the events so far.

        This is the O(n) reference implementation; `simulate` uses an
        incremental running sum instead for O(1) per-step intensity.
        """
        cfg = self.config
        lam = cfg.baseline_rate
        for e in self.events:
            dt = t - e.time
            if dt > 0.0:
                lam += cfg.alpha * np.exp(-cfg.beta * dt)
        return lam

    def simulate(self, duration: float) -> list[Spike]:
        """Simulate the process for `duration` seconds (Ogata's thinning).

        Returns the list of spikes (also stored in `self.events`). Spikes
        carry a Gaussian-distributed amplitude around `amplitude_mean`.

        Uses an incremental running sum for the excitation term so each
        acceptance check is O(1) rather than O(n).
        """
        if duration <= 0.0:
            raise ValueError("duration must be positive")

        cfg = self.config
        self.events = []
        t = 0.0
        # Running excitation sum: Σ_i α · exp(-β · (t - t_i)), evaluated at the
        # current time t. Decays exponentially as t advances; gets a fresh α
        # added on each accepted event.
        excitation = 0.0
        last_t = 0.0  # time at which `excitation` was last computed
        # Upper bound on the intensity (see comment below).
        lam_bar = cfg.baseline_rate + cfg.alpha * 5.0

        while t < duration:
            # Time to the next proposed event from the upper-bound Poisson.
            u = self._rng.random()
            t += -np.log(u + 1e-300) / lam_bar
            if t >= duration:
                break
            # Decay the running excitation sum to the current proposal time.
            excitation *= np.exp(-cfg.beta * (t - last_t))
            last_t = t
            # Accept with probability λ(t) / lam_bar.
            lam = cfg.baseline_rate + excitation
            if self._rng.random() <= lam / lam_bar:
                amp = self._rng.normal(cfg.amplitude_mean, cfg.amplitude_std)
                self.events.append(Spike(time=t, amplitude=float(amp)))
                # New event contributes α immediately (exp(-β·0) = 1).
                excitation += cfg.alpha
        return self.events

    def inter_spike_intervals(self) -> np.ndarray:
        """Array of inter-spike intervals (seconds)."""
        if len(self.events) < 2:
            return np.array([], dtype=np.float64)
        return np.diff(self.times)


def simulate_electrode(
    config: HawkesConfig | None = None,
    duration: float = 3600.0,
    channel: int = 0,
) -> HawkesProcess:
    """Simulate one electrode's spike train for `duration` seconds.

    `channel` is used to derive a per-channel seed so each of the 16 channels
    in the grid produces independent but reproducible spike trains.
    """
    cfg = config or HawkesConfig()
    per_channel_seed = cfg.seed + channel
    channel_cfg = HawkesConfig(
        baseline_rate=cfg.baseline_rate,
        alpha=cfg.alpha,
        beta=cfg.beta,
        amplitude_mean=cfg.amplitude_mean,
        amplitude_std=cfg.amplitude_std,
        seed=per_channel_seed,
    )
    proc = HawkesProcess(channel_cfg)
    proc.simulate(duration)
    return proc
