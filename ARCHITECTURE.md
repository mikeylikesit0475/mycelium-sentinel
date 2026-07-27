# Mycelium Sentinel — Architecture

> Owner: architect. Nothing gets built that isn't described here first.
> Portfolio archetype: **embedded / IoT / edge**. Languages: **Rust** (firmware) +
> **Python** (simulator, ML). Source concept: `Innovative Google ADK Kit Uses.md` §1.

## 0. What this project actually demonstrates

The source concept — reading mycelial electrophysiology to detect soil contamination —
cannot be validated without a lab, a cultivated substrate, and months of ground truth. This
repo does not claim to validate it.

**What it demonstrates is a hardware-in-the-loop embedded workflow with no hardware:** real
Rust firmware, running as a real binary inside an emulator, fed by a physics-based sensor
simulator over a virtual UART, tested in CI. That is a genuinely useful and
under-demonstrated engineering practice, and it is the interview story.

| Layer | Real or simulated |
|-------|-------------------|
| Mycelial spike trains | **Simulated** — Hawkes process parameterised from published fungal electrophysiology |
| Contaminant transport | **Simulated** — 2D advection–diffusion |
| Electrode/ADC front end | **Simulated** — 1/f noise, mains hum, DC drift, motion artifact |
| **Firmware** | **Real.** Rust `no_std`, compiled for the target, executed in Renode |
| **DSP** (filtering, spike detection, feature extraction) | **Real**, running inside the emulated MCU |
| Transport, ingest, storage, dashboard | **Real** |
| Classifier accuracy | **Not evidence about fungi.** The simulator generates the labels. It validates the pipeline. Stated in the README. |

The last row is the one that must never be softened. Because the simulator produces both
the signal and the label, a high classification score is close to tautological. The README
says so in the first paragraph.

## 1. The one demo everything serves

1. `make sim-up`. A 16-electrode grid over a simulated substrate begins publishing.
   Grafana shows 16 channels of irregular baseline spiking — sub-millivolt to a few
   millivolts, minutes-scale inter-spike intervals, matching published statistics.
2. `make firmware-up`. **Renode boots the actual firmware binary.** Show the Renode console
   — this is running compiled Rust, not a Python mock.
3. `make inject-plume CONTAMINANT=cadmium ORIGIN=3,1`. A plume begins diffusing from the
   grid corner.
4. Channels nearest the origin shift first: spike rate rises, amplitude distribution
   changes. Visible in Grafana before any threshold trips.
5. The firmware's on-MCU spike detector raises an event over the virtual UART. The edge
   classifier labels it `heavy-metal` with a confidence.
6. **The lead-time readout:** detection fired at simulated T+14 min; the plume reaches the
   grid centre at T+31 min. The gap is the product claim, and it is measured.
7. The firmware's PWM output — read out of Renode's emulated GPIO — actuates a virtual
   neutralisation valve. The simulator shows the plume arrested.
8. `make test` in a terminal: **the same firmware binary, tested in CI, no board.**

**The interview line:** *"The firmware under test is the real binary. I run it in Renode
against a physics simulator over a virtual UART, so embedded code gets CI without hardware
in the loop. The biology is simulated and I'd never claim otherwise — but the firmware,
the DSP and the test harness are the parts I'd bring to a real board unchanged."*

## 2. Component map

```
  ┌─────────────────────────┐        ┌──────────────────────────────┐
  │ sim/  (Python)          │        │ Renode                       │
  │  advection–diffusion    │        │  ┌────────────────────────┐  │
  │  Hawkes spike model     │ virtual│  │ firmware (Rust, no_std)│  │
  │  electrode/ADC model    │  UART  │  │  HP filter → notch     │  │
  │  16 channels ───────────┼───────▶│  │  MAD spike detect      │  │
  │  sim-clock (accelerated)│        │  │  feature extraction    │  │
  └─────────────────────────┘        │  │  event framing         │  │
             ▲                       │  └───────────┬────────────┘  │
             │ valve actuation       │   emulated GPIO/PWM  │ UART  │
             └───────────────────────┼──────────────────────┘       │
                                     └──────────────┬───────────────┘
                                                    │ events
                                     ┌──────────────▼───────────────┐
                                     │ ingest/ (Python)             │
                                     │  MQTT → classifier → alert   │
                                     │  TimescaleDB → Grafana       │
                                     └──────────────────────────────┘
```

## 3. The simulator

| Element | Model | Source |
|---------|-------|--------|
| Substrate | 32 × 32 cell grid, 16 electrodes on a 4 × 4 sub-grid | — |
| Contaminant transport | 2D advection–diffusion, `∂C/∂t = D∇²C − v·∇C` | standard |
| Baseline spiking | Hawkes process per electrode; self-excitation gives the bursty clustering seen in real recordings — a plain Poisson process looks obviously wrong | Adamatzky *et al.* fungal electrophysiology, cited in `docs/sources.md` |
| Contaminant response | Local concentration modulates Hawkes intensity λ and spike amplitude | **Illustrative — flagged as a guess.** No published dose-response curve was found; this is the weakest link and the README says so |
| Electrode front end | 1/f noise, 50 Hz mains + harmonics, slow DC drift, occasional motion artifact | standard instrumentation |

**Sim-clock acceleration.** Real mycelial spikes have inter-spike intervals of minutes to
hours. A real-time demo would be unwatchable. The simulator runs on an accelerated clock
with a configurable factor, and **the factor is displayed in the UI at all times** so the
demo never implies real-time detection.

## 4. Firmware — and why the target is what it is

Rust, `no_std`, running in **Renode**.

> **Target selection is a deliberate decision, not a default.** The concept implies an
> ESP32-class part, but Renode's ESP32 support is immature. We target an **nRF52840 or
> STM32F4** instead, because emulator fidelity matters more than a hypothetical bill of
> materials for a board we will never buy. This trade — choosing the part your test harness
> can actually model — is ADR-002 and is worth being able to defend.

On-MCU signal chain, all in the emulated device:

1. Sample ingestion from the virtual UART (stands in for an ADS1115-class ADC).
2. High-pass IIR — removes electrode DC drift.
3. 50 Hz notch — removes mains hum.
4. **MAD-based adaptive threshold** spike detection. Median absolute deviation rather than
   a fixed threshold, because electrode noise floors differ per channel and drift over time.
5. Feature extraction: inter-spike-interval statistics, amplitude histogram, burst index.
6. Event framing → UART out. **Features, not raw samples** — the bandwidth argument that
   justifies doing any of this on the MCU at all.

## 5. The classifier

Runs in `ingest/`, not on the MCU.

**Start with gradient-boosted trees, not a neural network.** The input is ~20 hand-designed
features from a spike train; this is exactly the regime where XGBoost beats a small CNN and
trains in seconds. A 1D-CNN over raw spike rasters goes in the table as a comparison only.

Both numbers in the README — and both under the standing caveat that the simulator produced
the labels.

## 6. Repository layout

```
sim/               transport PDE, Hawkes model, electrode model, sim clock
firmware/          Rust no_std: DSP chain, feature extraction, UART protocol
  tests/           on-target tests run under Renode
renode/            platform description, .resc scripts, virtual UART bridge
ingest/            MQTT consumer, classifier, alerting
deploy/            docker compose: mosquitto, TimescaleDB, Grafana
dashboards/        provisioned Grafana dashboards
docs/              ADRs, sources.md, interview stories
```

## 7. Testing — the actual point of the repo

| Layer | What | CI |
|-------|------|----|
| Unit (host) | DSP blocks compiled for host: filter response, MAD threshold behaviour | yes |
| **On-target** | **Firmware binary runs under Renode, fed a canned waveform, asserts the expected events on UART** | **yes** |
| Unit | Simulator: diffusion conserves mass; Hawkes ISI distribution matches the target | yes |
| Integration | Full loop: inject plume → assert detection within a lead-time bound | yes |
| Regression | Detection lead time doesn't degrade below a recorded floor | yes |

Row 2 is the reason this repo exists. **Renode runs headless in GitHub Actions** — the
whole embedded test suite runs on a runner with no hardware attached, and the CI badge
proves it.

## 8. Known risks

| Risk | Mitigation |
|------|-----------|
| Renode learning curve; platform description files are fiddly | Sprint 0 is dedicated to getting *one* trivial firmware blinking under Renode in CI before any DSP exists. If Renode can't be made to work in a week, **the project stops** — without it there is no story here. |
| Contaminant dose-response is invented | Flagged as illustrative in `docs/sources.md`, in the config, and in the README. It is the honest weak point; naming it is better than burying it. |
| Sim-clock acceleration reads as cheating | Factor displayed in the UI at all times and stated in the demo script. |
| Classifier accuracy is close to tautological | Stated in the README's first paragraph. The repo's claim is about the harness, not the biology. |
| Scope creep toward real electrodes and a substrate culture | Parking lot. No wet lab. |
