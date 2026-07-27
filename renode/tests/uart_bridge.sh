#!/usr/bin/env bash
# Virtual UART bridge integration test (Sprint 0.4).
#
# Boots the firmware in headless Renode with UART4 wired to a TCP server socket,
# then runs the Python bridge client which sends a framed message and asserts
# the firmware echoes it back as an ACK frame.
#
# Usage: renode/tests/uart_bridge.sh [port]
#
# Exits 0 on success, non-zero on any failure.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
RESC="$ROOT/renode/stm32f4_mycelium.resc"
BIN="$ROOT/target/thumbv7em-none-eabi/release/firmware-bin"
PORT="${1:-34567}"

if [ ! -f "$BIN" ]; then
    echo "FAIL: firmware binary not found at $BIN" >&2
    echo "      build it with: make firmware-build" >&2
    exit 2
fi

WORK="$(mktemp -d -t mycelium-bridge-XXXXXX)"
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

# Keep a write end of the FIFO open so Renode's stdin doesn't see EOF.
exec 9>"$FIFO" &

# Boot Renode: load the resc, create a server-socket terminal on $PORT, connect
# it to UART4, and run for 10 minutes of virtual time (blocks and keeps the
# emulator alive while the bridge client talks to the socket).
renode --disable-xwt --console \
    -e "\$bin=\"$BIN\"" \
    -e "i @$RESC" \
    -e "emulation CreateServerSocketTerminal $PORT \"term\" false" \
    -e "connector Connect sysbus.uart4 term" \
    -e 'emulation RunFor "00:10:00"' \
    <"$FIFO" >"$RENODE_LOG" 2>&1 &
RENODE_PID=$!

# Wait for the socket to bind and the firmware to boot.
for _ in $(seq 1 20); do
    if ss -lnt 2>/dev/null | grep -q ":$PORT"; then
        break
    fi
    sleep 0.25
done

if ! ss -lnt 2>/dev/null | grep -q ":$PORT"; then
    echo "FAIL: renode did not bind socket on port $PORT" >&2
    echo "--- renode log ---" >&2
    cat "$RENODE_LOG" >&2
    exit 1
fi

# Run the bridge client against the socket.
# Fall back to python3 if the uv venv isn't present (e.g. in CI where the Renode
# job doesn't sync the Python env).
PYTHON="${SPECTRAL_SCOUT_PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
fi
if "$PYTHON" "$ROOT/renode/bridge/uart_bridge.py" 127.0.0.1 "$PORT"; then
    echo "PASS: virtual UART bridge round-trip succeeded"
    exit 0
fi

echo "FAIL: bridge client reported failure" >&2
echo "--- renode log (tail) ---" >&2
tail -40 "$RENODE_LOG" >&2
exit 1