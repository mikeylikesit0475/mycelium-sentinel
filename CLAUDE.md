# Working agreement for AI assistants in this repo

Read [`ARCHITECTURE.md`](ARCHITECTURE.md) before writing code. It is the contract.
[`DECISIONS.md`](DECISIONS.md) explains *why*. Supersede an ADR in writing rather than
quietly diverging.

## Non-negotiables

1. **The claim is about the harness, not the biology.** The README's first paragraph states
   the simulation boundary and that the classifier's accuracy is close to tautological. Do
   not soften either. ADR-001.
2. **Renode on-target testing in CI is the reason this repo exists.** If you find yourself
   replacing the emulator with a Python mock of the MCU, stop — you have deleted the
   project. ADR-003.
3. **DSP stays on the emulated MCU.** Filtering, spike detection and feature extraction do
   not migrate to the host. The MCU emits features, never raw samples. ADR-005.
4. **The sim-clock acceleration factor is displayed in the UI at all times.** ADR-006.
5. **The invented dose-response coupling is flagged in the config, `docs/sources.md`, and a
   named weak-point section in the README.** Three places. ADR-008.
6. **XGBoost is the primary classifier**; the CNN is a comparison row. ADR-007.

## Conventions

- Firmware DSP blocks are written so they compile for the host too, so they get fast unit
  tests *and* on-target tests. Don't let a block become emulator-only.
- Every simulator constant is cited in `docs/sources.md` or carries an inline comment saying
  it's a guess. No exceptions — this repo's credibility is entirely in its caveats.
- The Hawkes ISI distribution has a statistical test against published values. Keep it
  passing.
- Detection lead time is reported as a **distribution across plume origins**, never a single
  run.
- `clippy -D warnings` and `ruff` are gates.

## The gate that stops the project

**Sprint 0.3** — a real firmware binary running under headless Renode in GitHub Actions with
an asserted on-target test, in a 4-hour box. **If it can't be done, stop and write up why.**
Do not proceed to Sprint 1 hoping to come back to it. Without Renode in CI this is a Python
simulator with extra steps and there is no reason to publish it.

## Environment notes for this machine

- Dev box is a Ryzen AI Max+ 395 on Fedora. Nothing here needs the GPU — XGBoost on ~20
  features trains in seconds on CPU. **Do not add a ROCm dependency**; gfx1151 is Preview
  tier and would buy nothing.
- **The XDNA2 NPU is unusable on Linux** (Vitis AI EP userspace wheel unpublished for
  x86_64 Linux). Do not write NPU code.

## Priority

This is the **lowest-priority** program in the satellite set. Build it when an embedded or
IoT posting justifies it, not speculatively. Say so if asked to start it without that
trigger.

## Working rhythm

Sprints and timeboxes are in `BACKLOG.md`. **Say when an item is going to blow its box.**
Each sprint ends with an interview story in `docs/interview-stories/`.
