"""Tests for the neutralisation valve model (Sprint 2.4)."""

from __future__ import annotations

from sim.transport import AdvectionDiffusionGrid, TransportConfig
from sim.valve import DEFAULT_NEUTRALISATION_RATE, ValveModel, run_closed_loop


def test_valve_starts_closed() -> None:
    valve = ValveModel()
    assert not valve.is_open


def test_open_close() -> None:
    valve = ValveModel()
    valve.open()
    assert valve.is_open
    valve.close()
    assert not valve.is_open


def test_closed_valve_does_not_affect_grid() -> None:
    grid = AdvectionDiffusionGrid(TransportConfig(dt=0.5))
    grid.inject(16, 16, mass=100.0)
    valve = ValveModel()
    mass_before = grid.total_mass
    for _ in range(100):
        grid.step()
        valve.step(grid)
    # Closed valve: mass is conserved by the transport (no-flux boundaries).
    assert abs(grid.total_mass - mass_before) < 1e-3


def test_open_valve_reduces_mass() -> None:
    grid = AdvectionDiffusionGrid(TransportConfig(dt=0.5))
    grid.inject(16, 16, mass=100.0)
    valve = ValveModel(rate=0.1)
    valve.open()
    mass_before = grid.total_mass
    for _ in range(100):
        grid.step()
        valve.step(grid)
    assert grid.total_mass < mass_before * 0.5, (
        f"open valve should reduce mass significantly: {grid.total_mass} vs {mass_before}"
    )


def test_closed_loop_arrests_plume() -> None:
    """A closed-loop run where the valve opens at step 50 should arrest the
    plume — the final mass should be less than the mass at detection."""
    result = run_closed_loop(
        origin=(3, 1),
        detection_step=50,
        total_steps=200,
        neutralisation_rate=0.1,
    )
    assert result["valve_was_open"]
    assert result["plume_arrested"], "plume should be arrested after valve opens"
    assert result["mass_at_end"] < result["mass_at_detection"]


def test_closed_loop_without_detection_does_not_arrest() -> None:
    """If the valve never opens (detection_step beyond the run), the plume
    is not arrested."""
    result = run_closed_loop(
        origin=(3, 1),
        detection_step=10_000,  # beyond total_steps
        total_steps=100,
        neutralisation_rate=0.1,
    )
    assert not result["valve_was_open"]
    assert not result["plume_arrested"]


def test_default_neutralisation_rate_is_documented() -> None:
    assert DEFAULT_NEUTRALISATION_RATE == 0.05
