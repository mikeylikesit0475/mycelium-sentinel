# Mycelium Sentinel — agent notes

Read [`ARCHITECTURE.md`](ARCHITECTURE.md) (the contract) and [`DECISIONS.md`](DECISIONS.md)
(the *why*) before writing code. [`CLAUDE.md`](CLAUDE.md) has the non-negotiables. This file
just pins down the environment so the next session doesn't have to rediscover it.

## Toolchain

- Rust toolchain via rustup (user-local, `~/.cargo/bin`). Stable 1.97. The embedded
  target `thumbv7em-none-eabi` is installed; `clippy` and `rustfmt` are present.
- Python via `uv` (workspace at repo root, members `sim/` and `ingest/`). `uv sync`
  sets up `.venv`. `pytest` and `pytest-cov` are in the `dev` dependency group.
- `ruff` is available standalone in `~/.local/bin` and also through `uv run ruff`.
- Renode 1.16.1 is installed user-local at `~/.local/renode/`, symlinked onto
  `~/.local/bin/renode`. It runs under system Mono 6.14. The platform description
  for the STM32F4 Discovery board lives in the Renode install
  (`~/.local/renode/platforms/boards/stm32f4_discovery-kit.repl`). The project's
  startup script is `renode/stm32f4_mycelium.resc`; it loads the firmware from
  `target/thumbv7em-none-eabi/release/firmware-bin` by default and the path can
  be overridden with `bin=...` on the `i @...resc` command (used by CI in 0.3).

## Commands

Run from the repo root.

| What | Command |
|------|---------|
| Host firmware unit tests (DSP, protocol) | `make test-host` |
| Build firmware binary for the embedded target | `make firmware-build` |
| Boot firmware in Renode (console) | `make renode-run` |
| Boot firmware in Renode headless, dump UART | `make renode-headless` |
| Clippy gate (host + target) | `make clippy` |
| Rustfmt gate | `make fmt-check` |
| Python lint | `make ruff` |
| Python tests | `make test-py` |
| All gates (CI parity) | `make lint` && `make test` |
| Sync Python env | `uv sync --all-packages` |

## Build matrix

- `firmware` is a Cargo workspace member that compiles two ways:
  - `no_std` for `thumbv7em-none-eabi` (the binary that boots in Renode) — built with
    `--features bin-build --bin firmware-bin`.
  - `std` for `x86_64-unknown-linux-gnu` (host unit tests of DSP blocks) — built with
    `--features std --target x86_64-unknown-linux-gnu`.
- The default Cargo target is the embedded one (`.cargo/config.toml`), so plain
  `cargo build` produces firmware. Host tests override the target explicitly.
- `unsafe_code = "deny"` is intentionally **not** workspace-wide: the binary needs
  the minimum unsafe for MMIO and the reset vector. The library blocks
  (`dsp.rs`, `protocol.rs`) stay unsafe-free by convention and review.

## Conventions that aren't obvious from the code

- Every simulator constant is cited in `docs/sources.md` or carries an inline
  comment saying it's a guess. No exceptions (CLAUDE.md).
- DSP blocks compile for the host too — `cargo test --features std` must pass for
  anything merged into `firmware/src/dsp.rs`. Don't let a block become
  emulator-only (CLAUDE.md, ADR-005).
- Lint gates: `clippy -D warnings` and `ruff`. Both must pass for CI green.