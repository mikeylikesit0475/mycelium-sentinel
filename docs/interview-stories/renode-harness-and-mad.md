# Interview Story: The Renode Harness and MAD Thresholding

> This is the "explain it back to me" prep (Sprint 2.8). Written cold, no
> notes, no code open. If I can't explain this without looking, I don't
> understand it well enough to defend in an interview.

## The Renode harness

The problem: embedded firmware needs to be tested on hardware, but hardware
isn't in the CI loop. The standard answer is "run unit tests on the host and
hope the on-target behaviour matches" — which is exactly the gap that bites
you in production.

This repo's answer: **run the real firmware binary in an instruction-level
emulator, feed it data over a virtual UART, and assert on its output — all
headless in CI.**

Concretely:

1. The firmware is real Rust `no_std`, compiled for `thumbv7em-none-eabi`
   (a Cortex-M4 target). It's the same binary that would run on a physical
   STM32F407 dev kit. No stubs, no host-mode shortcuts.
2. **Renode** is an instruction-level emulator (not a functional mock) — it
   models the CPU, the UART peripheral, the GPIO ports, the flash and SRAM
   memory map, the NVIC. The firmware's MMIO writes to real register
   addresses (UART4 at 0x4000_4C00, GPIO D at 0x4002_0C00) are intercepted
   by the emulator's peripheral models.
3. The simulator (Python) generates a canned waveform and streams it to the
   firmware over a **TCP socket wired to the emulated UART RX**. The firmware
   polls the UART, decodes sample frames, runs the DSP chain, detects spikes,
   extracts features, and writes event frames to UART TX — which come back
   out the TCP socket to the host.
4. The test harness asserts the firmware detected the right number of spikes
   with valid features. This runs in GitHub Actions on an Ubuntu runner with
   no board attached. The CI badge proves it.

The key decision (ADR-003): **Renode in CI is the go/no-go gate.** Sprint 0
was dedicated to proving this works before any DSP was written. If Renode
couldn't be made to work headless in CI, the project would stop — without it
there's no story, just a Python simulator with extra steps.

The tradeoff (ADR-002): the concept implies an ESP32, but Renode's ESP32
support is immature. We target an STM32F407 instead because **emulator
fidelity outweighs the bill of materials for a board we will never buy.**
When the test harness is the deliverable, choose the hardware your harness
can model.

## MAD-based adaptive thresholding

The problem: spike detection needs a threshold, but every electrode has a
different noise floor and that floor drifts over time. A fixed voltage
threshold is wrong on day one and worse on day ten.

This repo's answer: **estimate the noise floor from the signal itself, per
channel, continuously, using the median absolute deviation (MAD).**

The math:

- The MAD is the median of |x - median(x)|. For Gaussian noise, the MAD
  relates to the standard deviation by `sigma ≈ MAD / 0.7561` (the 0.7561
  is the normalising constant for the Gaussian).
- We maintain a rolling window of the last 512 samples (about 0.5 seconds
  at 1 kHz). On each sample, we compute the MAD over the window, convert to
  a sigma estimate, and set the threshold at `k * sigma` where k=5.
- A spike fires when a sample exceeds 5 sigma above the (high-passed)
  baseline. A refractory period (30 samples = 30 ms) prevents double-firing
  on the biphasic undershoot.

Why MAD and not plain standard deviation? **MAD is robust to outliers.** The
spikes themselves are outliers — if you compute the std dev of a signal that
contains spikes, the spikes inflate the std dev, which raises the threshold,
which makes you miss spikes. The median is barely affected by a few large
values, so the MAD gives you a clean noise-floor estimate even when spikes
are present in the window.

Why per-channel? Because the simulator deliberately gives each of the 16
electrodes a different noise floor (the electrode model's 1/f noise is
seeded per channel). A loud channel should not fire on a small blip that a
quiet channel would catch — and with MAD, it doesn't. The threshold adapts
to each channel independently.

The implementation constraint: this runs on a Cortex-M4 with no heap. The
rolling window is a fixed-size ring buffer (512 × 4 bytes = 2 KB per
channel, 32 KB for 16 channels — fits comfortably in the F407's 192 KB
SRAM). The MAD computation is an O(n) scan over the window per sample,
which at 512 samples and 125 MIPS is cheap. No allocation, no std, constant
time per sample — and the same code compiles for the host so the host unit
tests exercise the exact same logic that runs on the device (ADR-005).

## What I'd bring to a real board unchanged

- The DSP chain: high-pass IIR, 50 Hz notch, MAD detector, feature extractor.
  These are `no_std`, alloc-free, host-testable. They'd run on an nRF52840
  dev kit with no changes.
- The wire protocol: the frame format and the streaming decoder.
- The test harness: the Renode `.resc` script and the Python bridge adapt to
  any Renode-supported target by changing the platform description.

What I'd change: the UART/GPIO init code is STM32F4-specific (register
addresses, RCC clock enables). On an nRF52840 that's a different HAL — but
it's a thin layer, and the DSP above it is portable.