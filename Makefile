# Mycelium Sentinel — make targets.
#
# All gates mirror CI exactly. `make lint && make test` is the local CI parity
# command. The Rust toolchain is expected on PATH (rustup install).

SHELL := /usr/bin/env bash

CARGO  := cargo
UV     := uv
RUFF   := $(UV) run ruff
PYTEST := $(UV) run pytest

HOST_TARGET := x86_64-unknown-linux-gnu
FW_BIN      := firmware-bin

.PHONY: help
help:
	@echo "Mycelium Sentinel — common targets:"
	@echo "  make firmware-build   build the no_std firmware binary for thumbv7em-none-eabi"
	@echo "  make test-host        host unit tests for DSP/protocol blocks"
	@echo "  make clippy           clippy -D warnings (host + target)"
	@echo "  make fmt-check        rustfmt gate"
	@echo "  make ruff             ruff lint + format check (sim, ingest)"
	@echo "  make test-py          pytest (sim, ingest)"
	@echo "  make lint             all lint gates"
	@echo "  make test             all test gates"
	@echo "  make ci               lint + test (CI parity)"

# --- Rust ---------------------------------------------------------------------

.PHONY: firmware-build
firmware-build:
	$(CARGO) build --release --features bin-build --bin $(FW_BIN)

.PHONY: test-host
test-host:
	$(CARGO) test --features std --target $(HOST_TARGET)

.PHONY: clippy
clippy:
	$(CARGO) clippy --features std --target $(HOST_TARGET) -- -D warnings
	$(CARGO) clippy --release --features bin-build --bin $(FW_BIN) -- -D warnings

.PHONY: fmt-check
fmt-check:
	$(CARGO) fmt --all -- --check

# --- Python -------------------------------------------------------------------

.PHONY: ruff
ruff:
	$(RUFF) format --check sim ingest
	$(RUFF) check sim ingest

.PHONY: test-py
test-py:
	$(PYTEST) sim ingest

# --- Aggregates ---------------------------------------------------------------

.PHONY: lint
lint: clippy fmt-check ruff

.PHONY: test
test: test-host test-py

.PHONY: ci
ci: lint test

# --- Convenience (non-gate) ---------------------------------------------------

.PHONY: fmt
fmt:
	$(CARGO) fmt --all
	$(RUFF) format sim ingest

.PHONY: sync
sync:
	$(UV) sync --all-packages

.PHONY: clean
clean:
	$(CARGO) clean
	$(UV) clean
	rm -rf .pytest_cache .ruff_cache .coverage