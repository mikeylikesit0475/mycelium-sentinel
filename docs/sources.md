# Sources

Every simulator constant is cited here or carries an inline comment saying it's a
guess. No exceptions (CLAUDE.md).

## Fungal electrophysiology

- Adamatzky, A. *et al.* — fungal spike trains, inter-spike interval statistics.
  **TODO (Sprint 0.6):** pin the specific paper(s), parameter values, and the
  tolerance used in `sim/tests/test_hawkes.py`.

## Contaminant dose-response

- **None found.** The coupling in `sim/` between local contaminant concentration
  and Hawkes intensity / spike amplitude is invented. It is flagged as illustrative
  in the config (`sim/sim/config.py`), here, and in the README's weak-point section
  (ADR-008). This is the most attackable part of the project and we point at it.

## Electrode / ADC front end

- 1/f noise, 50 Hz mains + harmonics, slow DC drift, motion artifact — standard
  instrumentation models. **TODO (Sprint 1.1):** cite the noise spectral density
  assumption and the mains amplitude.

## Advection–diffusion

- 2D advection–diffusion `∂C/∂t = D∇²C − v·∇C` — standard PDE, no citation needed.
  Diffusion coefficient `D` and velocity `v` are guesses; flagged in the config
  when Sprint 0.5 lands them.