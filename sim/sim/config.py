"""Simulator configuration.

Centralises all the simulator's parameters in one place so the illustrative
guesses are visible and citable. Per CLAUDE.md, every constant is either
cited in `docs/sources.md` or flagged as a guess here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sim.clock import DEFAULT_FACTOR
from sim.coupling import DEFAULT_K_AMP, DEFAULT_K_RATE, CouplingConfig
from sim.electrode import (
    DEFAULT_DRIFT_AMP,
    DEFAULT_MAINS_AMP,
    DEFAULT_MAINS_FREQ,
    DEFAULT_MOTION_AMP,
    DEFAULT_MOTION_RATE,
    DEFAULT_NOISE_FLOOR,
    DEFAULT_SAMPLE_RATE,
    ElectrodeConfig,
)
from sim.hawkes import (
    DEFAULT_ALPHA,
    DEFAULT_AMPLITUDE_MEAN,
    DEFAULT_AMPLITUDE_STD,
    DEFAULT_BASELINE_RATE,
    DEFAULT_BETA,
    HawkesConfig,
)
from sim.transport import (
    DEFAULT_ADVECTION,
    DEFAULT_DIFFUSION,
    DEFAULT_DT,
    DEFAULT_GRID_SIZE,
    TransportConfig,
)


def _default_transport() -> TransportConfig:
    return TransportConfig(
        grid_size=DEFAULT_GRID_SIZE,
        diffusion=DEFAULT_DIFFUSION,
        advection=DEFAULT_ADVECTION,
        dt=DEFAULT_DT,
    )


def _default_hawkes() -> HawkesConfig:
    return HawkesConfig(
        baseline_rate=DEFAULT_BASELINE_RATE,
        alpha=DEFAULT_ALPHA,
        beta=DEFAULT_BETA,
        amplitude_mean=DEFAULT_AMPLITUDE_MEAN,
        amplitude_std=DEFAULT_AMPLITUDE_STD,
    )


def _default_electrode() -> ElectrodeConfig:
    return ElectrodeConfig(
        sample_rate=DEFAULT_SAMPLE_RATE,
        mains_freq=DEFAULT_MAINS_FREQ,
        mains_amp=DEFAULT_MAINS_AMP,
        drift_amp=DEFAULT_DRIFT_AMP,
        noise_floor=DEFAULT_NOISE_FLOOR,
        motion_amp=DEFAULT_MOTION_AMP,
        motion_rate=DEFAULT_MOTION_RATE,
    )


def _default_coupling() -> CouplingConfig:
    # ILLUSTRATIVE — no published dose-response curve (ADR-008).
    return CouplingConfig(k_rate=DEFAULT_K_RATE, k_amp=DEFAULT_K_AMP)


@dataclass(slots=True)
class SimConfig:
    """Top-level simulator configuration.

    Brings together the transport, Hawkes, electrode, coupling, and clock
    configs. The contaminant coupling is ILLUSTRATIVE (ADR-008) — flagged
    here, in `docs/sources.md`, and in the README.
    """

    transport: TransportConfig = field(default_factory=_default_transport)
    hawkes: HawkesConfig = field(default_factory=_default_hawkes)
    electrode: ElectrodeConfig = field(default_factory=_default_electrode)
    # ILLUSTRATIVE — no published dose-response curve (ADR-008).
    coupling: CouplingConfig = field(default_factory=_default_coupling)
    sim_clock_factor: float = DEFAULT_FACTOR
