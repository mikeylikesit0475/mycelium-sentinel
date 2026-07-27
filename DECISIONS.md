# Architecture Decision Records — Mycelium Sentinel

Format: context → decision → consequence.

---

## ADR-001 — The claim is about the harness, not the biology

**Context.** The source concept proposes detecting soil contamination from mycelial
electrophysiology. Validating that needs a wet lab, a cultivated substrate, and months of
ground truth. We have none of those.

**Decision.** The repo makes no claim about fungi. Its stated contribution is a
hardware-in-the-loop embedded workflow: real firmware, in an emulator, driven by a physics
simulator, tested in CI without a board. The README says this in the first paragraph.

**Consequence.** The classifier's accuracy figure is close to tautological — the simulator
generates both the signal and the label — and the README says that too. What survives
scrutiny is the firmware, the DSP and the test harness, all of which would transfer to a
real board unchanged. An interviewer who reads the first paragraph knows exactly what
they're being shown, which is the only version of this project worth publishing.

---

## ADR-002 — Target the part the emulator models well, not the part the concept implies

**Context.** The concept implies an ESP32-class MCU. Renode's ESP32 support is immature;
its nRF52840 and STM32F4 platforms are mature and well documented.

**Decision.** Target nRF52840 (or STM32F4 — decided in Sprint 0.2 on whichever proves
smoother). Emulator fidelity outweighs the bill of materials for a board that will never be
purchased.

**Consequence.** The demo becomes reliable and CI-testable. If the project ever moves to
real hardware, an nRF52840 dev kit is ~£40 — cheaper than the ESP32-plus-instrumentation
path anyway. The generalisable point, and the reason this is an ADR: **when the test harness
is the deliverable, choose the hardware your harness can model.**

---

## ADR-003 — Renode in CI is the go/no-go gate

**Context.** It would be easy to build the Python simulator first and treat the emulator as
a later nice-to-have. That ordering is how the emulator ends up cut.

**Decision.** Sprint 0.3 gates the entire project: a real firmware binary running under
headless Renode in GitHub Actions with an asserted on-target test, inside a 4-hour box. If
it can't be done, **the project stops** and the reason is written up.

**Consequence.** We risk a week and stop, rather than discovering at Sprint 2 that the only
differentiator was never achievable. Without Renode this repo is a Python simulator with
extra steps and no reason to exist next to the other four satellites.

---

## ADR-004 — MAD-based adaptive thresholding, not a fixed threshold

**Context.** A fixed voltage threshold is simpler.

**Decision.** Spike detection uses a median-absolute-deviation adaptive threshold per
channel.

**Consequence.** It survives channels with different noise floors and floors that drift over
time — which is the actual condition in any real electrode array, and which the simulator
reproduces deliberately so the choice is exercised rather than theoretical. Costs a running
median on an MCU; that constraint is itself a good thing to have solved.

---

## ADR-005 — The MCU emits features, not samples

**Context.** The firmware could stream raw ADC samples and let the host do everything.

**Decision.** Filtering, spike detection and feature extraction happen on the emulated MCU.
Only event frames carrying ~20 features cross the UART.

**Consequence.** This is the only thing that justifies an MCU in the architecture at all —
a three-order-of-magnitude bandwidth reduction, which in a real deployment is the difference
between a solar-powered node and a mains-powered one. If the DSP moved to the host, the
firmware would be a serial cable and the project would have no embedded story.

---

## ADR-006 — Simulator clock acceleration is displayed, never implied away

**Context.** Real mycelial inter-spike intervals are minutes to hours. A real-time demo is
unwatchable.

**Decision.** Configurable acceleration factor, **displayed in the UI at all times** and
stated aloud in the demo script.

**Consequence.** The demo is watchable in two minutes and cannot be mistaken for real-time
detection. A viewer who spots an unexplained time compression stops trusting everything
else on screen; showing it costs nothing and protects the rest.

---

## ADR-007 — Gradient-boosted trees before a neural network

**Context.** The classifier input is ~20 hand-designed features from a spike train.

**Decision.** XGBoost is the primary model. A 1D-CNN over raw spike rasters is a comparison
row only.

**Consequence.** Trains in seconds, gives interpretable feature importances, and is the
correct tool for tabular features. The CNN is there to answer "did you try deep learning?"
with a number rather than an opinion. Both live under the ADR-001 caveat, so neither number
is the point.

---

## ADR-008 — The invented dose-response is named as the weak point

**Context.** No published dose-response curve linking soil contaminant concentration to
mycelial spiking behaviour was found. The coupling in `sim/` is invented.

**Decision.** Flag it as illustrative in three places: the config file, `docs/sources.md`,
and a named weak-point section in the README.

**Consequence.** The most attackable part of the project is the part it points at itself.
That converts a potential "this is fabricated" objection into a demonstration of knowing
where the evidence runs out — which is the more valuable signal.
