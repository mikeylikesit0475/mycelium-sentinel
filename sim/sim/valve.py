"""Neutralisation valve model for the closed-loop simulation (Sprint 2.4).

When the firmware detects a spike, it drives GPIO D pin 12 high (the valve
actuation line). The simulator reads that GPIO state via Renode and opens the
neutralisation valve, which arrests the contaminant plume: the concentration
field decays exponentially while the valve is open.

This closes the loop: plume -> spike -> detection -> GPIO -> valve -> plume
arrested. ARCHITECTURE.md §1 beat 7.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sim.transport import AdvectionDiffusionGrid

DEFAULT_NEUTRALISATION_RATE: float = 0.05  # per step — guess, flagged in docs


@dataclass(slots=True)
class ValveModel:
    """A neutralisation valve that arrests the plume when open.

    When `open`, the concentration field is multiplied by
    `(1 - rate)` each step on top of the transport update. The rate is a
    guess flagged in `docs/sources.md`.
    """

    rate: float = DEFAULT_NEUTRALISATION_RATE
    _open: bool = False

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def step(self, grid: AdvectionDiffusionGrid) -> None:
        """Apply one neutralisation step to the grid if the valve is open."""
        if not self._open:
            return
        # Decay the concentration field. This is a simple first-order
        # neutralisation model — the real chemistry would be specific to the
        # contaminant and the neutralising agent, which we don't model.
        grid.concentration *= 1.0 - self.rate
        # Clip tiny negatives from floating-point noise.
        np.clip(grid.concentration, 0.0, None, out=grid.concentration)


def run_closed_loop(
    origin: tuple[int, int],
    detection_step: int,
    total_steps: int,
    transport_dt: float = 0.5,
    neutralisation_rate: float = DEFAULT_NEUTRALISATION_RATE,
) -> dict:
    """Run a closed-loop simulation: plume diffuses, at `detection_step` the
    valve opens, and we measure how the plume is arrested.

    Returns a summary dict with the total mass before and after the valve
    opened, and the mass at the end of the run.
    """
    from sim.transport import TransportConfig

    grid = AdvectionDiffusionGrid(TransportConfig(dt=transport_dt))
    grid.inject(origin[0], origin[1], mass=1000.0)
    valve = ValveModel(rate=neutralisation_rate)

    mass_before_valve = grid.total_mass
    mass_at_detection = 0.0
    mass_at_end = 0.0

    for step in range(total_steps):
        grid.step()
        valve.step(grid)
        if step == detection_step:
            valve.open()
            mass_at_detection = grid.total_mass
        if step == total_steps - 1:
            mass_at_end = grid.total_mass

    return {
        "mass_before_valve": mass_before_valve,
        "mass_at_detection": mass_at_detection,
        "mass_at_end": mass_at_end,
        "valve_opened_at_step": detection_step,
        "valve_was_open": valve.is_open,
        "plume_arrested": mass_at_end < mass_at_detection,
    }
