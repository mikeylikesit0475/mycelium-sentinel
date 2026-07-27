"""Contaminant -> spike-response coupling (ILLUSTRATIVE — ADR-008).

No published dose-response curve linking soil contaminant concentration to
mycelial spiking behaviour was found. The coupling here is invented and is
flagged as the project's honest weak point in three places: this file,
`docs/sources.md`, and the README's weak-point section (ADR-008).

The model: local contaminant concentration `C` (in arbitrary units) modulates
the Hawkes process parameters:

  - baseline rate:    mu_eff  = mu * (1 + k_rate * C)
  - spike amplitude:  amp_eff = amp * (1 + k_amp * C)

`k_rate` and `k_amp` are guesses. The effect is monotonic (more contaminant ->
higher rate, larger amplitudes), which is what the demo needs to show the
"channels nearest the origin shift first" story. It is NOT evidence about
fungi — the README says so in the first paragraph.
"""

from __future__ import annotations

from dataclasses import dataclass

# ILLUSTRATIVE PARAMETERS — guesses, not measurements (ADR-008).
DEFAULT_K_RATE: float = 5.0  # rate multiplier per unit concentration
DEFAULT_K_AMP: float = 0.5  # amplitude multiplier per unit concentration


@dataclass(frozen=True, slots=True)
class CouplingConfig:
    """Configuration for the contaminant -> spike-response coupling.

    ILLUSTRATIVE — these parameters are guesses. No published dose-response
    curve was found (ADR-008). Flagged in `docs/sources.md` and the README.
    """

    k_rate: float = DEFAULT_K_RATE
    k_amp: float = DEFAULT_K_AMP

    def __post_init__(self) -> None:
        if self.k_rate < 0.0:
            raise ValueError("k_rate must be non-negative (monotonic increase assumption)")
        if self.k_amp < 0.0:
            raise ValueError("k_amp must be non-negative (monotonic increase assumption)")


@dataclass(frozen=True, slots=True)
class CoupledHawkesParams:
    """Hawkes parameters after applying the contaminant coupling."""

    baseline_rate: float
    amplitude_mean: float
    amplitude_std: float
    concentration: float


def apply_coupling(
    baseline_rate: float,
    amplitude_mean: float,
    amplitude_std: float,
    concentration: float,
    config: CouplingConfig | None = None,
) -> CoupledHawkesParams:
    """Apply the contaminant coupling to Hawkes parameters.

    Returns the effective baseline rate and amplitude after the local
    contaminant concentration modulates them. ILLUSTRATIVE (ADR-008).
    """
    cfg = config or CouplingConfig()
    if concentration < 0.0:
        raise ValueError("concentration must be non-negative")
    mu_eff = baseline_rate * (1.0 + cfg.k_rate * concentration)
    amp_eff = amplitude_mean * (1.0 + cfg.k_amp * concentration)
    # Scale the amplitude std proportionally so the CV stays roughly constant.
    amp_std_eff = amplitude_std * (1.0 + cfg.k_amp * concentration)
    return CoupledHawkesParams(
        baseline_rate=mu_eff,
        amplitude_mean=amp_eff,
        amplitude_std=amp_std_eff,
        concentration=concentration,
    )
