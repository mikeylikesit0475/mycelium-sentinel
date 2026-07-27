# Mycelium Sentinel — Backlog & Sprint Plan

Scrum master's file. **If an item blows its box it gets cut or split, not extended.**

Two sprints plus a hard go/no-go gate in Sprint 0. This is the **lowest-priority** program
in the satellite set — build it only when an embedded or IoT posting justifies it.

## Definition of done (every sprint)

- [ ] Working demo of the sprint goal, no code edits
- [ ] Tests green in CI — **including the Renode on-target suite**
- [ ] `DEMO_SCRIPT.md` updated to match reality
- [ ] One interview story in `docs/interview-stories/`

## Definition of done (whole repo)

README leading with the **simulation boundary statement**, a CI badge showing embedded
tests passing with no hardware, architecture sketch, demo GIF · tests · Dockerfile ·
2-minute live demo.

---

## Sprint 0 — Emulator or bust · goal: *"real firmware runs in CI with no board"*

**This sprint contains the project's go/no-go gate.** Without Renode in CI there is no
interview story here, only a Python simulator with extra steps. Prove it before building
anything else.

| # | Item | Box | Done when |
|---|------|-----|-----------|
| 0.1 | Repo init: Cargo workspace, Python `uv` project, clippy + ruff, CI skeleton | 3h | Green CI on empty suites |
| 0.2 | **Renode spike:** pick the target (nRF52840 vs STM32F4), get a trivial `no_std` Rust binary running under Renode locally | 5h | Renode console shows firmware output |
| 0.3 | **GATE — Renode headless in GitHub Actions.** Same binary, asserted output, on a runner | 4h | **CI badge green with an on-target test. If this can't be done in the box, stop the project and record why in `docs/`.** |
| 0.4 | Virtual UART bridge: host process ↔ emulated device, framed protocol | 4h | Host sends bytes, firmware echoes structured frames |
| 0.5 | `sim/`: advection–diffusion grid + mass-conservation test | 4h | Plume diffuses correctly; test passes |
| 0.6 | `sim/`: Hawkes spike model, parameters cited; ISI distribution test | 4h | Generated ISI matches published statistics within tolerance |

**Demo:** Renode boots real firmware; a simulated plume diffuses in a plot; CI is green with
an on-target test. **Total ~24h.**

---

## Sprint 1 — The signal chain · goal: *"the MCU finds the spikes"*

| # | Item | Box | Done when |
|---|------|-----|-----------|
| 1.1 | Electrode/ADC model: 1/f noise, 50 Hz hum, DC drift, motion artifact | 3h | Waveforms look like real electrophysiology, not clean synthetics |
| 1.2 | Firmware DSP: high-pass IIR + 50 Hz notch, host-testable | 4h | Filter response asserted in host unit tests |
| 1.3 | **MAD-based adaptive spike detection** on-MCU | 5h | Detects spikes across channels with different noise floors |
| 1.4 | Feature extraction on-MCU: ISI stats, amplitude histogram, burst index | 4h | Event frames carry features, not raw samples |
| 1.5 | **On-target Renode test:** canned waveform in → expected events out | 4h | Runs in CI |
| 1.6 | MQTT publish from `ingest/`; TimescaleDB + Grafana via compose | 4h | 16 live channels visible in Grafana |
| 1.7 | Sim-clock acceleration + **factor displayed in the UI** | 2h | Never ambiguous whether this is real-time |

**Demo:** 16 channels of realistic baseline activity in Grafana, spikes detected by
firmware running in the emulator. **Total ~26h.**

---

## Sprint 2 — Detection, actuation, polish · goal: *"interview-ready"*

| # | Item | Box | Done when |
|---|------|-----|-----------|
| 2.1 | Contaminant → spike-response coupling, **flagged illustrative everywhere** | 3h | Config, docs and README all carry the caveat |
| 2.2 | XGBoost classifier on spike features; a 1D-CNN as comparison only | 5h | Both in the table, both under the standing caveat |
| 2.3 | **Detection lead time** metric: detection T vs. plume-arrival T | 4h | Measured, with a distribution across plume origins — not a single lucky run |
| 2.4 | PWM valve actuation out of Renode's emulated GPIO → simulator arrests the plume | 4h | Closed loop visible end to end |
| 2.5 | Lead-time regression floor asserted in CI | 3h | Degradation fails the build |
| 2.6 | README: **boundary statement first**, CI badge, honest weak-point section | 4h | The dose-response guess is named, not hidden |
| 2.7 | Demo GIF + finalise `DEMO_SCRIPT.md` | 3h | Matches reality |
| 2.8 | **"Explain it back to me"** — explain the Renode harness and MAD thresholding cold | 2h | Done without notes |

**Total ~28h.** Program total ≈ **78h**.

---

## Parking lot

- Real electrodes + a cultivated substrate (a wet lab, not a sprint)
- Multi-node mesh: several MCUs, LoRa transport
- Power modelling: duty cycling and a solar budget
- Renode co-simulation of the analog front end
- Deploying the same binary to a physical nRF52840 dev kit (~£40 — the cheapest way to make
  the whole story real, and the best parking-lot item here)
