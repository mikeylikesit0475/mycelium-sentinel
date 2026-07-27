# Mycelium Sentinel

> **The biology here is simulated and I'd never claim otherwise.** What's real
> is the firmware, the signal processing, and the test harness — a
> hardware-in-the-loop embedded workflow with no hardware. That's what this
> repo demonstrates, and it's the interview story. The classifier's accuracy
> is close to tautological because the simulator produces both the signal and
> the label; the README says so in this first paragraph. (ADR-001.)

[![CI](https://github.com/user/mycelium-sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/user/mycelium-sentinel/actions/workflows/ci.yml)

## What this is

A hardware-in-the-loop embedded workflow for an environmental sensor concept
(reading mycelial electrophysiology to detect soil contamination) — built
without a lab, a cultivated substrate, or a physical board. **Real Rust
`no_std` firmware**, compiled for an STM32F407, executes inside **Renode**,
fed by a **physics-based sensor simulator** over a **virtual UART**, with the
whole embedded test suite running **in CI on a GitHub runner with no hardware
attached**.

That last point is the reason this repo exists. Embedded projects usually
can't run on-target tests in CI; this one does, and the badge above proves it.

## The simulation boundary

| Layer | Real or simulated |
|-------|-------------------|
| Mycelial spike trains | **Simulated** — Hawkes process parameterised from published fungal electrophysiology |
| Contaminant transport | **Simulated** — 2D advection–diffusion |
| Electrode/ADC front end | **Simulated** — 1/f noise, mains hum, DC drift, motion artifact |
| **Firmware** | **Real.** Rust `no_std`, compiled for the target, executed in Renode |
| **DSP** (filtering, spike detection, feature extraction) | **Real**, running inside the emulated MCU |
| Transport, ingest, storage, dashboard | **Real** |
| Classifier accuracy | **Not evidence about fungi.** The simulator generates the labels. |

## The one demo

1. `make sim-up` — simulator + mosquitto + TimescaleDB + Grafana start.
2. `make firmware-up` — Renode boots the actual firmware binary.
3. `make inject-plume CONTAMINANT=cadmium ORIGIN=3,1` — a plume diffuses.
4. Channels nearest the origin shift first: spike rate rises, amplitudes change.
5. The firmware's on-MCU spike detector raises an event over the virtual UART.
6. The lead-time readout: detection at simulated T+14 min; plume reaches the
   grid centre at T+31 min. The gap is the product claim, measured across a
   distribution of plume origins.
7. The firmware's PWM output — read out of Renode's emulated GPIO — actuates a
   virtual neutralisation valve. The simulator shows the plume arrested.
8. `make test` — the same firmware binary, tested in CI, no board.

## The interview line

> *"The firmware under test is the real binary. I run it in Renode against a
> physics simulator over a virtual UART, so embedded code gets CI without
> hardware in the loop. The biology is simulated and I'd never claim otherwise
> — but the firmware, the DSP and the test harness are the parts I'd bring to
> a real board unchanged."*

## Repository layout

```
sim/               transport PDE, Hawkes model, electrode model, sim clock
firmware/          Rust no_std: DSP chain, feature extraction, UART protocol
  tests/           on-target tests run under Renode
renode/            .resc scripts, virtual UART bridge, on-target tests
ingest/            MQTT consumer, classifier, alerting
deploy/            docker compose: mosquitto, TimescaleDB, Grafana
dashboards/        provisioned Grafana dashboards
docs/              ADRs, sources.md, interview stories
```

## Quick start

```bash
# Build and test everything (CI parity):
make ci

# Boot the firmware in Renode and see the banner:
make renode-run

# Run the on-target signal-chain test (canned waveform in, events out):
make signal-chain-test
```

See [`AGENTS.md`](AGENTS.md) for the full command reference,
[`ARCHITECTURE.md`](ARCHITECTURE.md) for the design contract, and
[`DECISIONS.md`](DECISIONS.md) for the ADRs (the *why*).

## Testing — the actual point of the repo

| Layer | What | CI |
|-------|------|----|
| Unit (host) | DSP blocks compiled for host: filter response, MAD threshold behaviour | yes |
| **On-target** | **Firmware binary runs under Renode, fed a canned waveform, asserts the expected events on UART** | **yes** |
| Unit | Simulator: diffusion conserves mass; Hawkes ISI distribution matches the target | yes |
| Integration | Full loop: inject plume → assert detection within a lead-time bound | yes |
| Regression | Detection lead time doesn't degrade below a recorded floor | yes |

Row 2 is the reason this repo exists. **Renode runs headless in GitHub Actions**
— the whole embedded test suite runs on a runner with no hardware attached,
and the CI badge proves it.

## Honest weak points

**The contaminant dose-response is invented.** No published dose-response
curve linking soil contaminant concentration to mycelial spiking behaviour was
found. The coupling in `sim/coupling.py` is a monotonic linear guess, flagged
as illustrative in three places: the config, `docs/sources.md`, and here. It is
the most attackable part of the project, and pointing at it is better than
burying it. (ADR-008.)

**The classifier's accuracy is close to tautological.** The simulator produces
both the signal and the label, so a high classification score is expected
rather than impressive. The repo's claim is about the harness, not the
biology. (ADR-001.)

**The sim clock is accelerated.** Real mycelial inter-spike intervals are
minutes to hours. The simulator runs on an accelerated clock with a
configurable factor, and the factor is displayed in the UI at all times so the
demo never implies real-time detection. (ADR-006.)

## Target selection

The concept implies an ESP32-class part, but Renode's ESP32 support is
immature. We target an **STM32F407** instead, because emulator fidelity matters
more than a hypothetical bill of materials for a board we will never buy. This
trade — choosing the part your test harness can actually model — is ADR-002 and
is worth being able to defend. If the project ever moves to real hardware, an
nRF52840 dev kit is ~£40 and runs the same binary.

## License

MIT OR Apache-2.0.