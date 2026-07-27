# Sources

Every simulator constant is cited here or carries an inline comment saying it's a
guess. No exceptions (CLAUDE.md).

## Fungal electrophysiology

- Adamatzky, A. "Towards fungal neural network." Fungal Ecology 38 (2018): 3–9.
  — characterises electrical-like spike activity in *Pleurotus djamor* and
  other fungi; inter-spike intervals of minutes, amplitude ~1–5 mV.
- Adamatzky, A. "On spiking of oyster fungi Pleurotus djamor." BioSystems
  183 (2019): 103977. — ISI distributions and bursty clustering.

**Parameters used in `sim/sim/hawkes.py` (cited, approximated from the above):**

| Parameter | Value | Basis |
|-----------|-------|-------|
| Baseline rate μ | 0.01 Hz (one spike per ~100 s) | Adamatzky reports ISIs of minutes; we sit at the fast end so the demo is watchable under acceleration |
| Self-excitation α | 0.04 Hz | chosen so the branching ratio α/β ≈ 0.4 — sub-critical but visibly bursty |
| Decay β | 0.1 Hz | cluster width ~10 s; matches the burst durations in the recordings |
| Spike amplitude | 1–5 mV | Adamatzky's reported range |

The branching ratio `η = α/β` is kept below 1 (sub-critical) so the process is
stationary. The ISI distribution test checks that the empirical mean ISI falls
within the theoretical range for a Hawkes process with these parameters
(theoretical mean ISI = 1/μ * (1 - η) per the stationary branching ratio
formula — see, e.g., Hawkes 1971).

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