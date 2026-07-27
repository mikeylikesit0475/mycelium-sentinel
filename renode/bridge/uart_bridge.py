"""Virtual UART bridge client for the Mycelium Sentinel firmware test.

Sprint 0.4: connects to the Renode UART socket terminal, sends a framed
message, and asserts the firmware echoes it back as an ACK frame. This is
the host side of the virtual UART bridge (ARCHITECTURE.md §2).

Used by `renode/tests/uart_bridge.sh` which boots Renode with a server-socket
terminal wired to UART4, then runs this client against it.
"""

from __future__ import annotations

import socket
import struct
import sys
import time

SOF = 0xA5
EOF_BYTE = 0x5A
ACK_MARKER = 0xAC


def encode_frame(channel: int, payload: bytes) -> bytes:
    if len(payload) > 64:
        raise ValueError("payload too long")
    return bytes([SOF, channel, len(payload)]) + payload + bytes([EOF_BYTE])


def decode_frame(buf: bytes) -> tuple[int, bytes] | None:
    if len(buf) < 4 or buf[0] != SOF:
        return None
    n = buf[2]
    if len(buf) < 3 + n + 1 or buf[3 + n] != EOF_BYTE:
        return None
    return buf[1], buf[3 : 3 + n]


def recv_exact(sock: socket.socket, n: int, timeout: float = 5.0) -> bytes:
    sock.settimeout(timeout)
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf.extend(chunk)
    return bytes(buf)


def recv_frame(sock: socket.socket, timeout: float = 5.0) -> tuple[int, bytes]:
    """Read one framed message from the socket, blocking until complete."""
    sock.settimeout(timeout)
    # Read header: SOF, channel, len.
    header = recv_exact(sock, 3, timeout)
    if header[0] != SOF:
        raise ValueError(f"expected SOF, got {header[0]:#x}")
    channel = header[1]
    n = header[2]
    rest = recv_exact(sock, n + 1, timeout)
    if rest[n] != EOF_BYTE:
        raise ValueError("missing EOF")
    return channel, rest[:n]


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 34567

    payload = struct.pack("<HHf", 7, 42, 1.5)
    sent = encode_frame(channel=3, payload=payload)

    print(f"[bridge] connecting to {host}:{port} ...")
    with socket.create_connection((host, port), timeout=10) as sock:
        # Wait briefly for the firmware boot banner to flush through.
        time.sleep(0.5)
        # Drain any banner bytes so they don't confuse the frame parser.
        sock.settimeout(0.5)
        try:
            while True:
                data = sock.recv(256)
                if not data:
                    break
                sys.stdout.write(f"[bridge] drained: {data!r}\n")
                sys.stdout.flush()
        except socket.timeout:
            pass

        print(f"[bridge] sending frame: {sent.hex()}")
        sock.sendall(sent)

        print("[bridge] waiting for echo ...")
        chan, echoed = recv_frame(sock, timeout=5.0)
        print(f"[bridge] received frame: channel={chan} payload={echoed.hex()}")

        if chan != 3:
            print(f"FAIL: expected channel 3, got {chan}", file=sys.stderr)
            return 1
        if not echoed or echoed[0] != ACK_MARKER:
            print(f"FAIL: expected ACK marker {ACK_MARKER:#x}, got {echoed!r}", file=sys.stderr)
            return 1
        if echoed[1:] != payload:
            print(f"FAIL: echoed payload mismatch: sent {payload.hex()}, got {echoed[1:].hex()}", file=sys.stderr)
            return 1

        print("PASS: firmware echoed frame with ACK marker")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())