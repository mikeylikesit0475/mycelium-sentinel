#!/usr/bin/env bash
# On-target signal-chain integration test (Sprint 1.5).
#
# Boots the firmware in headless Renode with UART4 wired to a TCP server socket,
# streams a canned waveform (noise + known spikes) as sample frames to channel
# 0, reads back event frames, and asserts the firmware detected approximately
# the right number of spikes. Proves the whole chain works on the emulated MCU:
# sample ingestion -> high-pass -> notch -> MAD spike detect -> features -> out.
#
# Usage: renode/tests/signal_chain.sh [port]
#
# Exits 0 on success, non-zero on any failure.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
RESC="$ROOT/renode/stm32f4_mycelium.resc"
BIN="$ROOT/target/thumbv7em-none-eabi/release/firmware-bin"
PORT="${1:-34568}"

if [ ! -f "$BIN" ]; then
    echo "FAIL: firmware binary not found at $BIN" >&2
    echo "      build it with: make firmware-build" >&2
    exit 2
fi

WORK="$(mktemp -d -t mycelium-chain-XXXXXX)"
FIFO="$WORK/stdin.fifo"
RENODE_LOG="$WORK/renode.log"
mkfifo "$FIFO"

cleanup() {
    if [ -n "${RENODE_PID:-}" ]; then
        kill "$RENODE_PID" 2>/dev/null || true
        wait "$RENODE_PID" 2>/dev/null || true
    fi
    exec 9>&- 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT

exec 9>"$FIFO" &

renode --disable-xwt --console \
    -e "\$bin=\"$BIN\"" \
    -e "i @$RESC" \
    -e "emulation CreateServerSocketTerminal $PORT \"term\" false" \
    -e "connector Connect sysbus.uart4 term" \
    -e 'emulation RunFor "00:30:00"' \
    <"$FIFO" >"$RENODE_LOG" 2>&1 &
RENODE_PID=$!

for _ in $(seq 1 20); do
    if ss -lnt 2>/dev/null | grep -q ":$PORT"; then
        break
    fi
    sleep 0.25
done

if ! ss -lnt 2>/dev/null | grep -q ":$PORT"; then
    echo "FAIL: renode did not bind socket on port $PORT" >&2
    cat "$RENODE_LOG" >&2
    exit 1
fi

if "$ROOT/.venv/bin/python" "$ROOT/renode/bridge/signal_chain.py" 127.0.0.1 "$PORT"; then
    echo "PASS: on-target signal-chain test succeeded"
    exit 0
fi

echo "FAIL: signal-chain test reported failure" >&2
echo "--- renode log (tail) ---" >&2
tail -40 "$RENODE_LOG" >&2
exit 1