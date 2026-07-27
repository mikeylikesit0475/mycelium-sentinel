"""Detection lead-time metric (Sprint 2.3).

The product claim: the firmware detects a contaminant plume *before* it reaches
the grid centre. The metric is the gap between:

  - **detection time**: the simulated virtual time at which the spike rate on
    the nearest electrode first exceeds a threshold (the firmware's detector
    would have fired by this point).
  - **arrival time**: the virtual time at which the plume's centre of mass
    reaches the grid centre.

The lead time is `arrival - detection`. A positive lead time means the
detection fired before the plume arrived — the product's value proposition.

Measured across a distribution of plume origins, not one lucky run
(ARCHITECTURE.md §1, beat 6).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sim.coupling import CouplingConfig, apply_coupling
from sim.hawkes import HawkesConfig
from sim.transport import AdvectionDiffusionGrid, TransportConfig


@dataclass(frozen=True, slots=True)
class LeadTimeResult:
    """The lead-time result for a single plume origin."""

    origin: tuple[int, int]
    detection_time: float  # virtual seconds
    arrival_time: float  # virtual seconds
    lead_time: float  # arrival - detection (positive = good)


def _electrode_offsets(grid_size: int, subgrid: int = 4) -> np.ndarray:
    return np.linspace(2, grid_size - 3, subgrid, dtype=int)


def _grid_centre(grid_size: int) -> tuple[float, float]:
    return (grid_size / 2.0, grid_size / 2.0)


def _plume_centre_of_mass(grid: AdvectionDiffusionGrid) -> tuple[float, float]:
    c = grid.concentration
    total = c.sum()
    if total <= 0.0:
        return (float(grid.config.grid_size) / 2.0, float(grid.config.grid_size) / 2.0)
    rows, cols = np.indices(c.shape)
    return (float((rows * c).sum() / total), float((cols * c).sum() / total))


def _arrival_time(
    grid: AdvectionDiffusionGrid,
    origin: tuple[int, int],
    centre_threshold: float = 0.05,
    max_steps: int = 50_000,
) -> float | None:
    """Run the transport grid forward until the plume's concentration at the
    grid centre exceeds `centre_threshold`. Returns the virtual time, or None
    if it never arrives within max_steps."""
    cx, cy = _grid_centre(grid.config.grid_size)
    cxi, cyi = int(cx), int(cy)
    for _ in range(max_steps):
        grid.step()
        if grid.concentration[cxi, cyi] > centre_threshold:
            return grid.time
    return None


def _detection_time(
    grid: AdvectionDiffusionGrid,
    origin: tuple[int, int],
    base_hawkes: HawkesConfig,
    coupling: CouplingConfig,
    rate_threshold_factor: float = 3.0,
    max_steps: int = 50_000,
) -> float | None:
    """Run the transport grid forward, sampling electrode readings, applying
    the coupling to get the effective Hawkes rate, and detecting when the
    nearest electrode's rate first exceeds `rate_threshold_factor` × baseline.
    Returns the virtual time, or None if it never fires within max_steps."""
    offsets = _electrode_offsets(grid.config.grid_size)
    # Find the electrode nearest the origin.
    distances = [
        (abs(r - origin[0]) + abs(c - origin[1]), i, j)
        for i, r in enumerate(offsets)
        for j, c in enumerate(offsets)
    ]
    distances.sort()
    _, nearest_i, nearest_j = distances[0]
    baseline_rate = base_hawkes.theoretical_mean_rate
    threshold = baseline_rate * rate_threshold_factor

    for _ in range(max_steps):
        grid.step()
        # Sample the concentration at the nearest electrode.
        conc = grid.concentration[offsets[nearest_i], offsets[nearest_j]]
        if conc <= 0.0:
            continue
        coupled = apply_coupling(
            baseline_rate=base_hawkes.baseline_rate,
            amplitude_mean=base_hawkes.amplitude_mean,
            amplitude_std=base_hawkes.amplitude_std,
            concentration=float(conc),
            config=coupling,
        )
        # Effective mean rate from the coupled Hawkes parameters.
        # Theoretical mean rate = mu_eff / (1 - eta), eta = alpha/beta (unchanged).
        eta = base_hawkes.alpha / base_hawkes.beta
        effective_rate = coupled.baseline_rate / (1.0 - eta)
        if effective_rate >= threshold:
            return grid.time
    return None


def measure_lead_time(
    origin: tuple[int, int],
    transport: TransportConfig | None = None,
    base_hawkes: HawkesConfig | None = None,
    coupling: CouplingConfig | None = None,
) -> LeadTimeResult:
    """Measure the lead time for a single plume origin.

    Runs two independent transport simulations from the same origin: one to
    find the detection time (spike rate threshold), one to find the arrival
    time (plume reaches the grid centre). Returns a LeadTimeResult.
    """
    transport = transport or TransportConfig()
    base_hawkes = base_hawkes or HawkesConfig()
    coupling = coupling or CouplingConfig()

    # Detection simulation.
    grid_det = AdvectionDiffusionGrid(transport)
    grid_det.inject(origin[0], origin[1], mass=1000.0)
    det_time = _detection_time(grid_det, origin, base_hawkes, coupling)

    # Arrival simulation (independent, same origin).
    grid_arr = AdvectionDiffusionGrid(transport)
    grid_arr.inject(origin[0], origin[1], mass=1000.0)
    arr_time = _arrival_time(grid_arr, origin)

    if det_time is None or arr_time is None:
        return LeadTimeResult(
            origin=origin,
            detection_time=float("inf"),
            arrival_time=float("inf"),
            lead_time=float("-inf"),
        )

    return LeadTimeResult(
        origin=origin,
        detection_time=det_time,
        arrival_time=arr_time,
        lead_time=arr_time - det_time,
    )


def measure_lead_time_distribution(
    origins: list[tuple[int, int]] | None = None,
    transport: TransportConfig | None = None,
    base_hawkes: HawkesConfig | None = None,
    coupling: CouplingConfig | None = None,
) -> list[LeadTimeResult]:
    """Measure lead time across a distribution of plume origins.

    By default uses a spread of origins near the grid corners/edges, per
    ARCHITECTURE.md §1 beat 6: 'measured across a distribution of plume
    origins, not one lucky run.'
    """
    if origins is None:
        # A spread of origins across the grid.
        origins = [(3, 1), (1, 3), (3, 3), (2, 1), (1, 2), (1, 1)]
    return [measure_lead_time(origin, transport, base_hawkes, coupling) for origin in origins]


def lead_time_summary(results: list[LeadTimeResult]) -> dict:
    """Summarise a distribution of lead-time results."""
    lead_times = np.array([r.lead_time for r in results if r.lead_time != float("-inf")])
    if lead_times.size == 0:
        return {
            "n": 0,
            "mean": float("nan"),
            "median": float("nan"),
            "min": float("nan"),
            "max": float("nan"),
            "all_positive": False,
        }
    return {
        "n": int(lead_times.size),
        "mean": float(lead_times.mean()),
        "median": float(np.median(lead_times)),
        "min": float(lead_times.min()),
        "max": float(lead_times.max()),
        "all_positive": bool((lead_times > 0).all()),
    }
