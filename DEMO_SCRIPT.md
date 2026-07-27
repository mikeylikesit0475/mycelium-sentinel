# Mycelium Sentinel — 2-Minute Demo Script

Live, no code edits. **Never describe a capability that doesn't work.**

> **Demo GIF:** `docs/demo.gif` (placeholder — record with `asciinema` or a
> screen capture during a live run). The GIF should show: the Renode console
> with the boot banner, the Grafana dashboard with the sim-clock factor
> visible, and the GitHub Actions CI tab going green.

## Pre-flight

```bash
make sim-up          # simulator + mosquitto + timescale + grafana (docker compose)
make firmware-up     # renode boots the firmware binary
open http://localhost:3000     # grafana (admin/admin)
```

Have the Renode console visible in a second window — **that window is the demo**. Have the
GitHub Actions run open in a browser tab for the closing beat.

---

## The script

**[0:00] State the boundary before anything else. This buys credit for everything after.**

> "Up front: the biology here is simulated and I'd never claim otherwise. What's real is
> the firmware, the signal processing, and the test harness. That's what I want to show you."

**[0:15] The baseline.**

Grafana, 16 channels.

> "Sixteen electrodes over a simulated substrate. The spiking is a Hawkes process — the
> self-excitation is what gives you that bursty clustering. A plain Poisson process looks
> obviously wrong next to real fungal recordings."

Point at the sim-clock indicator.

> "And note the clock factor in the corner. Real inter-spike intervals are minutes to hours,
> so this is accelerated. It's on screen the whole time so there's no ambiguity."

**[0:35] The Renode window. This is the centrepiece — make them look at it.**

> "This is Renode. That's not a Python mock of a microcontroller — it's a compiled Rust
> `no_std` binary for an nRF52840, executing. The simulator feeds it samples over a virtual
> UART, exactly where a real ADC would sit."

> "The filtering, the spike detection and the feature extraction are all happening in there.
> The MCU emits about twenty features per event, not raw samples — that's a thousand-fold
> bandwidth reduction, and it's the only reason there's a microcontroller in this design
> at all."

**[1:00] Inject the plume.**

```bash
make inject-plume CONTAMINANT=cadmium ORIGIN=3,1
```

> "Cadmium plume, advection–diffusion from the corner. Watch the channels nearest the origin."

Spike rate and amplitude shift on the near channels.

**[1:20] Detection and lead time.**

> "The firmware's adaptive threshold trips — median absolute deviation per channel, not a
> fixed voltage, because every electrode has a different noise floor and it drifts."

Point at the lead-time readout.

> "Detection at simulated T+14 minutes. The plume reaches the grid centre at T+31. That
> seventeen-minute gap is the metric, and it's measured across a distribution of plume
> origins, not one lucky run."

**[1:35] The closed loop.**

> "The firmware drives a PWM output — that's Renode's emulated GPIO — and the simulator
> reads it as a neutralisation valve. Plume arrested. The loop closes through emulated
> hardware."

**[1:45] The actual point. Switch to the GitHub Actions tab.**

> "And this is what I'd want a hiring manager to take away: that entire embedded test suite
> runs in CI. Real firmware binary, on-target assertions, on a GitHub runner with no board
> attached. Embedded projects usually can't do that, and it's the reason I built it this
> way."

**[1:55] Close on the weak point. Volunteer it.**

> "The honest weak point: I couldn't find a published dose-response curve linking
> contaminant concentration to spiking behaviour, so that coupling is invented. It's flagged
> in the config, the docs and the README. Which also means the classifier's accuracy number
> is close to tautological — the simulator made the labels. The harness is the contribution."

---

## Questions to have answers ready for

| Question | Answer lives in |
|----------|-----------------|
| "Isn't this all just simulated?" | Yes — and you said so first. The firmware, DSP and CI harness are real and transfer to a board unchanged. ADR-001. |
| "Why nRF52840 and not ESP32?" | ADR-002 — Renode models it well. Choose the part your harness can model. Good answer; have it ready. |
| "Why do the DSP on the MCU at all?" | ADR-005 — bandwidth. Solar-powered node vs. mains-powered node. |
| "How would you validate the biology?" | Cultivated substrate, Ag/AgCl electrodes, controlled dosing, months of ground truth. Say the honest scope. |
| "What's the cheapest path to making it real?" | A ~£40 nRF52840 dev kit runs the same binary. Parking lot. |
