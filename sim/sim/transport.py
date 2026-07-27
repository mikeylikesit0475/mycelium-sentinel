"""2D advection-diffusion solver for the Mycelium Sentinel substrate.

Solves `∂C/∂t = D∇²C − v·∇C` on a 32×32 cell grid using a finite-difference
scheme with reflecting (no-flux) boundaries so the total contaminant mass is
conserved. The grid hosts a 4×4 electrode sub-grid (16 channels).

Model constants are guesses flagged in `docs/sources.md` and the config — there
is no published dose-response curve for mycelial electrophysiology vs. soil
contaminants (ADR-008). The transport model itself is standard PDE.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_GRID_SIZE: int = 32
DEFAULT_DIFFUSION: float = 0.01  # m^2/s — guess, flagged in docs/sources.md
DEFAULT_ADVECTION: tuple[float, float] = (0.002, 0.0)  # m/s — guess
DEFAULT_DT: float = 0.1  # s — integration step
ELECTRODE_SUBGRID: int = 4  # 4x4 electrodes on the 32x32 grid


@dataclass(frozen=True, slots=True)
class TransportConfig:
    """Configuration for the advection-diffusion solver.

    All constants are guesses flagged in `docs/sources.md` (ADR-008).
    """

    grid_size: int = DEFAULT_GRID_SIZE
    diffusion: float = DEFAULT_DIFFUSION
    advection: tuple[float, float] = DEFAULT_ADVECTION
    dt: float = DEFAULT_DT

    def __post_init__(self) -> None:
        if self.grid_size < 4:
            raise ValueError("grid_size must be at least 4")
        if self.diffusion < 0.0:
            raise ValueError("diffusion coefficient must be non-negative")
        if self.dt <= 0.0:
            raise ValueError("dt must be positive")


class AdvectionDiffusionGrid:
    """A 2D advection-diffusion grid with no-flux (reflecting) boundaries.

    The grid is square, `n × n` cells. Concentration is stored as a float array;
    total mass is conserved exactly by the no-flux boundary treatment.
    """

    def __init__(self, config: TransportConfig | None = None) -> None:
        self.config = config or TransportConfig()
        n = self.config.grid_size
        self.concentration = np.zeros((n, n), dtype=np.float64)
        self._time = 0.0

    @property
    def time(self) -> float:
        """Simulated time elapsed (seconds)."""
        return self._time

    @property
    def total_mass(self) -> float:
        """Total contaminant mass on the grid (sum of all cells)."""
        return float(self.concentration.sum())

    def inject(self, row: int, col: int, mass: float) -> None:
        """Inject `mass` units of contaminant at grid cell (row, col)."""
        n = self.config.grid_size
        if not (0 <= row < n and 0 <= col < n):
            raise IndexError(f"({row}, {col}) out of bounds for {n}x{n} grid")
        if mass < 0.0:
            raise ValueError("mass must be non-negative")
        self.concentration[row, col] += mass

    def step(self) -> None:
        """Advance the simulation by one `dt` step.

        Uses an explicit finite-difference scheme in conservative (flux-
        divergence) form: `∂C/∂t = -∇·F` where `F = v·C - D·∇C`. The flux is
        evaluated at cell faces and set to zero at the grid walls, so total
        mass is conserved exactly (no mass crosses the boundary).
        """
        c = self.concentration
        dt = self.config.dt
        d = self.config.diffusion
        vx, vy = self.config.advection
        n = self.config.grid_size

        # Face concentrations (average of the two cells sharing a face).
        # x-faces: shape (n, n+1); face [i, j] is between cell (i, j-1) and (i, j).
        cx_face = np.empty((n, n + 1), dtype=c.dtype)
        cx_face[:, 1:-1] = 0.5 * (c[:, :-1] + c[:, 1:])
        # Boundary faces: zero flux (no-flux walls).
        cx_face[:, 0] = 0.0
        cx_face[:, -1] = 0.0
        # y-faces: shape (n+1, n); face [i, j] is between cell (i-1, j) and (i, j).
        cy_face = np.empty((n + 1, n), dtype=c.dtype)
        cy_face[1:-1, :] = 0.5 * (c[:-1, :] + c[1:, :])
        cy_face[0, :] = 0.0
        cy_face[-1, :] = 0.0

        # Diffusive flux at faces: F_diff = -D * ∇C ≈ -D * (C_right - C_left) / dx.
        # With dx = 1.
        diff_flux_x = np.zeros_like(cx_face)
        diff_flux_x[:, 1:-1] = -d * (c[:, 1:] - c[:, :-1])
        diff_flux_y = np.zeros_like(cy_face)
        diff_flux_y[1:-1, :] = -d * (c[1:, :] - c[:-1, :])

        # Advective flux at faces: F_adv = v * C_face.
        adv_flux_x = vx * cx_face
        adv_flux_y = vy * cy_face

        # Total flux.
        flux_x = adv_flux_x + diff_flux_x
        flux_y = adv_flux_y + diff_flux_y

        # Divergence of flux at each cell: (F_x[i, j+1] - F_x[i, j]) + (F_y[i+1, j] - F_y[i, j]).
        div_flux = (flux_x[:, 1:] - flux_x[:, :-1]) + (flux_y[1:, :] - flux_y[:-1, :])

        # Update: ∂C/∂t = -∇·F.
        self.concentration = c - dt * div_flux
        self._time += dt

    def step_for(self, seconds: float) -> None:
        """Advance the simulation by `seconds` of simulated time."""
        n_steps = max(1, round(seconds / self.config.dt))
        for _ in range(n_steps):
            self.step()

    def electrode_readings(self) -> np.ndarray:
        """Sample the concentration at the 4×4 electrode sub-grid.

        Electrodes are spaced evenly across the grid. Returns a 4×4 array of
        concentrations, one per channel.
        """
        n = self.config.grid_size
        # Place electrodes at evenly-spaced interior cells, skipping the edges.
        offsets = np.linspace(2, n - 3, ELECTRODE_SUBGRID, dtype=int)
        return self.concentration[np.ix_(offsets, offsets)].copy()
