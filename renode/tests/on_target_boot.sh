#!/usr/bin/env bash
# On-target firmware test for Mycelium Sentinel (Sprint 0.3, ADR-003).
#
# Boots the real firmware binary in headless Renode, captures UART4 output to a
# file, and asserts the boot banner appears. This is the CI go/no-go gate: if
# this can't pass on a GitHub runner with no board attached, the project stops
# (BACKLOG.md Sprint 0.3, ADR-003).
#
# Usage: renode/tests/on_target_boot.sh [path/to/firmware-bin]
#
# Exits 0 on success, non-zero on any failure.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
RESC="$ROOT/renode/stm32f4_mycelium.resc"

BIN="${1:-$ROOT/target/thumbv7em-none-eabi/release/firmware-bin}"

if [ ! -f "$BIN" ]; then
    echo "FAIL: firmware binary not found at $BIN" >&2
    echo "      build it with: make firmware-build" >&2
    exit 2
fi

WORK="$(mktemp -d -t mycelium-renode-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

UART_DUMP="$WORK/uart.txt"
RENODE_LOG="$WORK/renode.log"
EXPECTED="[mycelium-sentinel] firmware 0.0.0 booted on STM32F407 (Renode)"

# Run Renode headless: load the resc with the firmware path overridden, wire
# UART4 to a file backend, run for 1s of virtual time, quit.
# Run Renode headless: set the firmware path variable, load the resc, wire
# UART4 to a file backend, run for 1s of virtual time, quit.
timeout 60 renode --disable-xwt --console \
    -e "\$bin=\"$BIN\"" \
    -e "i @$RESC" \
    -e "uart4 CreateFileBackend @$UART_DUMP true" \
    -e "start" \
    -e 'emulation RunFor "00:00:01"' \
    -e "quit" >"$RENODE_LOG" 2>&1 || {
    echo "FAIL: renode invocation failed (see $RENODE_LOG)" >&2
    cat "$RENODE_LOG" >&2
    exit 1
}

if [ ! -f "$UART_DUMP" ]; then
    echo "FAIL: UART dump file was not created (see $RENODE_LOG)" >&2
    cat "$RENODE_LOG" >&2
    exit 1
fi

echo "--- UART output ---"
cat "$UART_DUMP"
echo "--- end UART output ---"

if grep -F -q "$EXPECTED" "$UART_DUMP"; then
    echo "PASS: boot banner found in UART output"
    exit 0
fi

echo "FAIL: boot banner not found in UART output" >&2
echo "expected: $EXPECTED" >&2
exit 1