"""On-target signal-chain test for the Mycelium Sentinel firmware (Sprint 1.5).

Boots the firmware in headless Renode with UART4 wired to a TCP server socket,
streams a canned waveform (noise + known spikes) as sample frames to channel 0,
reads back event frames, and asserts the firmware detected approximately the
right number of spikes.

This is the integration test that proves the whole chain works on the emulated
MCU: sample ingestion → high-pass → notch → MAD spike detect → feature
extraction → event frame out. (ARCHITECTURE.md §7, row 2.)
"""

from __future__ import annotations

import socket
import struct
import sys
import threading
import time

import numpy as np

SOF = 0xA5
EOF_BYTE = 0x5A


def encode_sample_frame(channel: int, sample: float) -> bytes:
    payload = struct.pack("<f", sample)
    return bytes([SOF, channel, len(payload)]) + payload + bytes([EOF_BYTE])


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
    header = recv_exact(sock, 3, timeout)
    if header[0] != SOF:
        raise ValueError(f"expected SOF, got {header[0]:#x}")
    channel = header[1]
    n = header[2]
    rest = recv_exact(sock, n + 1, timeout)
    if rest[n] != EOF_BYTE:
        raise ValueError("missing EOF")
    return channel, rest[:n]


# SpikeFeatures layout — must match firmware/src/features.rs SpikeFeatures.
# #[repr(C)] on ARM/x86 with 4-byte align: u8 at 0, 3 bytes padding, then
# 11 x f32 starting at offset 4, then [u8; 8] at offset 48. Total 56 bytes.
FEATURES_FMT = "<B3x11f8B"
FEATURES_SIZE = struct.calcsize(FEATURES_FMT)


def decode_features(payload: bytes) -> dict | None:
    if len(payload) < FEATURES_SIZE:
        return None
    fields = struct.unpack(FEATURES_FMT, payload[:FEATURES_SIZE])
    return {
        "count": fields[0],
        "amplitude": fields[1],
        "amplitude_mean": fields[2],
        "amplitude_std": fields[3],
        "amplitude_min": fields[4],
        "amplitude_max": fields[5],
        "isi_mean": fields[6],
        "isi_std": fields[7],
        "isi_min": fields[8],
        "isi_max": fields[9],
        "burst_index": fields[10],
        "rate": fields[11],
        "histogram": list(fields[12:20]),
    }


def make_canned_waveform(seed: int = 12345) -> tuple[np.ndarray, list[int]]:
    """A canned waveform: Gaussian noise + clear spikes at known indices.

    Returns (samples, spike_indices). The spikes are tall enough (amplitude 3.0
    vs noise sigma ~0.02) that the MAD detector should fire on each.
    """
    rng = np.random.default_rng(seed)
    n = 1200
    noise_sigma = 0.02
    samples = rng.standard_normal(n) * noise_sigma
    # Place 4 spikes at well-separated indices, each a brief positive pulse.
    # All spikes are after the 512-sample detector window fills.
    spike_indices = [700, 850, 1000, 1150]
    for idx in spike_indices:
        for off in range(-1, 2):
            if 0 <= idx + off < n:
                samples[idx + off] += 3.0
    return samples, spike_indices


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 34567
    channel = 0  # test on channel 0

    samples, expected_spikes = make_canned_waveform()
    print(f"[chain] canned waveform: {len(samples)} samples, {len(expected_spikes)} known spikes")

    print(f"[chain] connecting to {host}:{port} ...")
    with socket.create_connection((host, port), timeout=10) as sock:
        # Wait for the firmware boot banner to flush through.
        time.sleep(0.5)
        sock.settimeout(0.5)
        try:
            while True:
                data = sock.recv(256)
                if not data:
                    break
        except socket.timeout:
            pass

        # Start a background thread that drains event frames while we send.
        # Without this the firmware's TX poll blocks on a full socket buffer
        # and stops reading RX — a classic flow-control deadlock.
        events: list[dict] = []
        stop = threading.Event()

        def drain_events() -> None:
            sock.settimeout(0.5)
            while not stop.is_set():
                try:
                    chan, payload = recv_frame(sock, timeout=0.5)
                    if chan == channel:
                        feats = decode_features(payload)
                        if feats is not None:
                            events.append(feats)
                except (socket.timeout, ValueError, ConnectionError, OSError):
                    continue

        reader = threading.Thread(target=drain_events, daemon=True)
        reader.start()

        # Stream the waveform as sample frames. Pace at roughly the UART baud
        # rate (115200 baud ~= 14400 bytes/s ~= 1.8 ms per 8-byte frame) so the
        # firmware's poll loop can read each frame without the RX FIFO
        # overflowing. Send slightly slower than the baud rate to leave headroom.
        print(f"[chain] streaming {len(samples)} samples to channel {channel} ...")
        for i, s in enumerate(samples):
            frame = encode_sample_frame(channel, float(s))
            sock.sendall(frame)
            time.sleep(0.002)

        # Give the firmware a moment to flush remaining events.
        time.sleep(1.0)
        stop.set()
        reader.join(timeout=2.0)

        print(f"[chain] received {len(events)} event frames")
        for i, e in enumerate(events[:5]):
            print(f"  event {i}: amp={e['amplitude']:.3f} count={e['count']} rate={e['rate']:.2f}")

        # Assert: the firmware should have detected approximately the right
        # number of spikes. We tolerate some over/under-counting (refractory
        # may merge adjacent pulses; noise may occasionally trip) but the
        # count should be in the right ballpark.
        n_expected = len(expected_spikes)
        n_detected = len(events)
        # Allow 50% under/over — the point is "the chain works end to end",
        # not a precise recall figure.
        if n_detected < n_expected // 2:
            print(
                f"FAIL: detected only {n_detected} events, expected ~{n_expected}",
                file=sys.stderr,
            )
            return 1
        if n_detected > n_expected * 2:
            print(
                f"FAIL: detected {n_detected} events, far more than {n_expected}",
                file=sys.stderr,
            )
            return 1

        # Each event should carry non-trivial features.
        for e in events:
            if e["amplitude"] < 1.0:
                print(f"FAIL: event amplitude too small: {e['amplitude']}", file=sys.stderr)
                return 1

        print(
            f"PASS: firmware detected {n_detected} spikes from the canned waveform "
            f"(expected ~{n_expected}), each with valid features"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())