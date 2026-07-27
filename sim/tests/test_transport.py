"""Tests for the advection-diffusion solver.

Sprint 0.5's 'Done when': plume diffuses correctly; mass-conservation test
passes. The mass-conservation test is the non-negotiable check — the no-flux
boundary treatment must keep total mass constant to floating-point tolerance.
"""

from __future__ import annotations

import numpy as np

from sim.transport import AdvectionDiffusionGrid, TransportConfig


def test_injection_adds_mass() -> None:
    grid = AdvectionDiffusionGrid()
    assert grid.total_mass == 0.0
    grid.inject(row=16, col=16, mass=100.0)
    assert grid.total_mass == 100.0


def test_mass_is_conserved_under_diffusion_only() -> None:
    """No-flux boundaries: total mass must not change under pure diffusion."""
    cfg = TransportConfig(diffusion=0.02, advection=(0.0, 0.0), dt=0.1)
    grid = AdvectionDiffusionGrid(cfg)
    grid.inject(row=16, col=16, mass=1000.0)
    initial = grid.total_mass
    for _ in range(500):
        grid.step()
    assert abs(grid.total_mass - initial) < 1e-6, f"mass drifted: {initial} -> {grid.total_mass}"


def test_mass_is_conserved_with_advection() -> None:
    """Advection moves mass around but cannot remove it (no-flux boundaries)."""
    cfg = TransportConfig(diffusion=0.01, advection=(0.005, 0.002), dt=0.1)
    grid = AdvectionDiffusionGrid(cfg)
    grid.inject(row=4, col=4, mass=500.0)
    initial = grid.total_mass
    for _ in range(1000):
        grid.step()
    assert abs(grid.total_mass - initial) < 1e-5, f"mass drifted: {initial} -> {grid.total_mass}"


def test_plume_spreads_out_from_point_source() -> None:
    """A point injection diffuses: the peak drops and neighbours rise."""
    cfg = TransportConfig(diffusion=0.05, advection=(0.0, 0.0), dt=0.1)
    grid = AdvectionDiffusionGrid(cfg)
    grid.inject(row=16, col=16, mass=100.0)
    peak_before = grid.concentration[16, 16]
    for _ in range(200):
        grid.step()
    peak_after = grid.concentration[16, 16]
    # Peak must have dropped — mass spread to neighbours.
    assert peak_after < peak_before
    # Immediate neighbours must have gained concentration.
    neighbours_after = (
        grid.concentration[15, 16]
        + grid.concentration[17, 16]
        + grid.concentration[16, 15]
        + grid.concentration[16, 17]
    )
    assert neighbours_after > 0.0


def test_advection_displaces_the_plume_centre() -> None:
    """With nonzero advection, the plume's centre of mass moves downwind."""
    cfg = TransportConfig(diffusion=0.005, advection=(0.01, 0.0), dt=0.1)
    grid = AdvectionDiffusionGrid(cfg)
    grid.inject(row=16, col=16, mass=100.0)

    def centre_of_mass() -> tuple[float, float]:
        c = grid.concentration
        total = c.sum()
        if total == 0.0:
            return (16.0, 16.0)
        rows, cols = np.indices(c.shape)
        return (float((rows * c).sum() / total), float((cols * c).sum() / total))

    com_before = centre_of_mass()
    for _ in range(2000):
        grid.step()
    com_after = centre_of_mass()
    # Positive x-advection moves the column-centre-of-mass rightward (cols increase).
    assert com_after[1] > com_before[1], f"plume did not move downwind: {com_before} -> {com_after}"


def test_electrode_readings_shape() -> None:
    grid = AdvectionDiffusionGrid()
    readings = grid.electrode_readings()
    assert readings.shape == (4, 4)
    assert readings.dtype == np.float64


def test_step_for_advances_time() -> None:
    grid = AdvectionDiffusionGrid(TransportConfig(dt=0.5))
    assert grid.time == 0.0
    grid.step_for(10.0)
    assert abs(grid.time - 10.0) < 1e-9


def test_invalid_config_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        TransportConfig(diffusion=-1.0)
    with pytest.raises(ValueError):
        TransportConfig(dt=0.0)
    with pytest.raises(ValueError):
        TransportConfig(grid_size=2)
