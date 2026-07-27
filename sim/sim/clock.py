"""Sim-clock acceleration for the Mycelium Sentinel simulator.

Real mycelial inter-spike intervals are minutes to hours. A real-time demo
would be unwatchable. The simulator runs on an accelerated clock with a
configurable factor, and **the factor is included in every event and
displayed in the UI at all times** so the demo never implies real-time
detection (ADR-006).

The SimClock wraps a monotonic wall clock and exposes a virtual time that
advances at `factor` × wall-clock rate. All simulator components (transport,
Hawkes, electrode) use virtual time; the firmware runs in real emulator
time but the sample stream is generated from the virtual timeline.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

DEFAULT_FACTOR: float = 60.0  # 1 wall second = 1 virtual minute


@dataclass(slots=True)
class SimClock:
    """An accelerated virtual clock.

    `factor` is the acceleration: virtual seconds per wall second. A factor
    of 60 means 1 wall second = 1 virtual minute. The factor must be > 0 and
    is exposed via `factor()` so the UI and event frames can display it.
    """

    factor: float = DEFAULT_FACTOR
    _origin_wall: float = 0.0
    _origin_virt: float = 0.0

    def __post_init__(self) -> None:
        if self.factor <= 0.0:
            raise ValueError("sim-clock factor must be positive")
        self._origin_wall = time.monotonic()
        self._origin_virt = 0.0

    def reset(self) -> None:
        """Reset the clock origin (virtual time back to 0)."""
        self._origin_wall = time.monotonic()
        self._origin_virt = 0.0

    def now(self) -> float:
        """Current virtual time in seconds."""
        wall = time.monotonic() - self._origin_wall
        return self._origin_virt + wall * self.factor

    def advance(self, virtual_seconds: float) -> None:
        """Manually advance the virtual time by `virtual_seconds`.

        Used when the simulator steps a PDE or Hawkes process by a fixed
        virtual-time increment that isn't tied to wall time.
        """
        self._origin_virt += virtual_seconds

    def factor_label(self) -> str:
        """A human-readable label for the UI, e.g. '60x (1s = 1min)'."""
        return f"{self.factor:g}x ({_factor_human(self.factor)})"


def _factor_human(factor: float) -> str:
    """Describe the wall-to-virtual ratio in human terms."""
    if factor >= 3600:
        return f"1s = {factor / 3600:g}h"
    if factor >= 60:
        return f"1s = {factor / 60:g}min"
    return f"1s = {factor:g}s"
