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
	@echo "  make renode-run        boot the firmware in Renode (console), 2s run"
	@echo "  make renode-headless   boot the firmware in Renode headless, dump UART"
	@echo "  make test-host         host unit tests for DSP/protocol blocks"
	@echo "  make clippy            clippy -D warnings (host + target)"
	@echo "  make fmt-check         rustfmt gate"
	@echo "  make ruff              ruff lint + format check (sim, ingest)"
	@echo "  make test-py           pytest (sim, ingest)"
	@echo "  make lint              all lint gates"
	@echo "  make test              all test gates"
	@echo "  make ci                lint + test (CI parity)"

# --- Rust ---------------------------------------------------------------------

.PHONY: firmware-build
firmware-build:
	$(CARGO) build --release --features bin-build --bin $(FW_BIN)

.PHONY: renode-run
renode-run: firmware-build
	renode --disable-xwt --console \
	  -e "i @renode/stm32f4_mycelium.resc" \
	  -e "start" \
	  -e 'emulation RunFor "00:00:02"' \
	  -e "quit"

.PHONY: renode-headless
renode-headless: firmware-build
	@rm -f /tmp/mycelium-uart.txt
	renode --disable-xwt --console \
	  -e "i @renode/stm32f4_mycelium.resc" \
	  -e "uart4 CreateFileBackend @/tmp/mycelium-uart.txt true" \
	  -e "start" \
	  -e 'emulation RunFor "00:00:01"' \
	  -e "quit" >/tmp/mycelium-renode.log 2>&1
	@echo "--- UART output ---"
	@cat /tmp/mycelium-uart.txt
	@echo "--- (renode log: /tmp/mycelium-renode.log) ---"

.PHONY: renode-test
renode-test: firmware-build
	./renode/tests/on_target_boot.sh

.PHONY: bridge-test
bridge-test: firmware-build
	./renode/tests/uart_bridge.sh

.PHONY: signal-chain-test
signal-chain-test: firmware-build
	./renode/tests/signal_chain.sh

.PHONY: valve-test
valve-test: firmware-build
	./renode/tests/valve_actuation.sh

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
test: test-host test-py renode-test bridge-test signal-chain-test valve-test

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

# --- Demo orchestration -------------------------------------------------------

.PHONY: sim-up
sim-up:
	docker compose -f deploy/docker-compose.yml up -d

.PHONY: sim-down
sim-down:
	docker compose -f deploy/docker-compose.yml down

.PHONY: firmware-up
firmware-up: firmware-build
	renode --disable-xwt --console \
	  -e "i @renode/stm32f4_mycelium.resc" \
	  -e "start" \
	  -e 'emulation RunFor "01:00:00"'

.PHONY: inject-plume
inject-plume:
	$(UV) run python -m sim.inject_plume --contaminant cadmium --origin 3,1