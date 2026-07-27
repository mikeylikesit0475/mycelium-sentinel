"""Live demo orchestrator — the full pipeline in one script.

Boots Renode with the firmware, generates 16 channels of realistic
electrophysiology (Hawkes spikes + electrode noise), streams them through
the firmware via the virtual UART, reads event frames back, publishes them
to MQTT, and the ingest consumer writes them to TimescaleDB for Grafana.

Usage:
    uv run python -m sim.demo              # runs for ~60s of wall time
    uv run python -m sim.demo --duration 120

This is the 'make demo' target — the visible demo piece that populates the
Grafana dashboard live.
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import subprocess
import sys
import threading
import time

import numpy as np

from sim.clock import SimClock
from sim.electrode import ElectrodeConfig, render_channel
from sim.hawkes import HawkesConfig, simulate_electrode

SOF = 0xA5
EOF_BYTE = 0x5A
NUM_CHANNELS = 4  # demo uses 4 channels (not 16) so each gets enough bandwidth
SAMPLE_RATE = 1000.0
UART_PORT = 34570


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


def recv_frame(sock: socket.socket, timeout: float = 1.0) -> tuple[int, bytes] | None:
    try:
        header = recv_exact(sock, 3, timeout)
        if header[0] != SOF:
            return None
        channel = header[1]
        n = header[2]
        rest = recv_exact(sock, n + 1, timeout)
        if rest[n] != EOF_BYTE:
            return None
        return channel, rest[:n]
    except (TimeoutError, ConnectionError, ValueError):
        return None


def generate_waveforms(duration_s: float, seed: int = 42) -> list[np.ndarray]:
    """Generate 16 channels of realistic electrophysiology.

    The Hawkes baseline rate is raised for the demo so spikes are visible in
    a few seconds of waveform (real ISIs are minutes — the sim-clock factor
    handles the time compression, ADR-006). The electrode model still adds
    realistic noise/hum/drift on top.
    """
    waveforms = []
    # Demo rate: 0.5 Hz = ~1 spike per 2s. Real rate is 0.01 Hz; the sim-clock
    # factor (60x) means 1 wall second = 1 virtual minute, so this is the
    # accelerated-time equivalent.
    demo_hawkes = HawkesConfig(
        baseline_rate=0.5, alpha=0.1, beta=0.5, amplitude_mean=5.0, amplitude_std=1.0, seed=seed
    )
    for ch in range(NUM_CHANNELS):
        ch_cfg = HawkesConfig(
            baseline_rate=demo_hawkes.baseline_rate,
            alpha=demo_hawkes.alpha,
            beta=demo_hawkes.beta,
            amplitude_mean=demo_hawkes.amplitude_mean,
            amplitude_std=demo_hawkes.amplitude_std,
            seed=seed + ch,
        )
        proc = simulate_electrode(ch_cfg, duration=duration_s, channel=ch)
        elec_cfg = ElectrodeConfig(
            sample_rate=SAMPLE_RATE,
            seed=seed + ch * 100,
            mains_amp=0.02,
            noise_floor=0.01,
            drift_amp=0.1,
            motion_amp=0.0,
            motion_rate=0.0,
        )
        _, voltage = render_channel(proc.events, duration_s, elec_cfg)
        waveforms.append(voltage)
    return waveforms


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the live demo pipeline.")
    parser.add_argument("--duration", type=float, default=60.0, help="wall seconds to run")
    parser.add_argument("--port", type=int, default=UART_PORT)
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    args = parser.parse_args()

    clock = SimClock(factor=60.0)
    print(f"[demo] sim-clock: {clock.factor_label()}")
    print(f"[demo] generating {NUM_CHANNELS} channels of electrophysiology...")

    # Generate 5 seconds of waveform per channel — enough for the 512-sample
    # detector window to fill (at the interleaved effective sample rate) and
    # for several spikes to fire after the window is full.
    wf_duration = 5.0
    waveforms = generate_waveforms(wf_duration, seed=42)
    n_samples = len(waveforms[0])
    print(f"[demo] {n_samples} samples per channel, {NUM_CHANNELS} channels")

    # Boot Renode with the UART socket.
    print(f"[demo] booting firmware in Renode (port {args.port})...")
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.dirname(root)
    resc = os.path.join(root, "renode", "stm32f4_mycelium.resc")
    bin_path = os.path.join(root, "target", "thumbv7em-none-eabi", "release", "firmware-bin")

    if not os.path.exists(bin_path):
        print(f"FAIL: firmware binary not found at {bin_path}", file=sys.stderr)
        print("      run: make firmware-build", file=sys.stderr)
        return 1

    import tempfile

    work = tempfile.mkdtemp(prefix="mycelium-demo-")
    fifo = os.path.join(work, "stdin.fifo")
    os.mkfifo(fifo)
    renode_log = os.path.join(work, "renode.log")

    fd9 = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)

    # SIM115: the file handle must stay open for the subprocess lifetime; we
    # close it explicitly in the cleanup section below.
    # ruff: noqa: SIM115
    renode_log_handle = open(renode_log, "w", encoding="utf-8")
    renode = subprocess.Popen(
        [
            "renode",
            "--disable-xwt",
            "--console",
            "-e",
            f'$bin="{bin_path}"',
            "-e",
            f"i @{resc}",
            "-e",
            f'emulation CreateServerSocketTerminal {args.port} "term" false',
            "-e",
            "connector Connect sysbus.uart4 term",
            "-e",
            'emulation RunFor "02:00:00"',
        ],
        stdin=fd9,
        stdout=renode_log_handle,
        stderr=subprocess.STDOUT,
    )

    # Connect MQTT publisher.
    import paho.mqtt.client as mqtt

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        mqtt_client.connect(args.mqtt_host, args.mqtt_port, 60)
        mqtt_client.loop_start()
        print(f"[demo] connected to MQTT at {args.mqtt_host}:{args.mqtt_port}")
    except Exception as e:
        print(f"[demo] MQTT not available, events will be printed only: {e}")
        mqtt_client = None

    # Wait for the socket.
    print("[demo] waiting for Renode socket...")
    for _ in range(40):
        try:
            sock = socket.create_connection(("127.0.0.1", args.port), timeout=2)
            break
        except OSError:
            time.sleep(0.25)
    else:
        print("FAIL: Renode did not bind the socket", file=sys.stderr)
        renode.kill()
        return 1

    print("[demo] connected to firmware UART")

    # Drain the boot banner.
    import contextlib

    sock.settimeout(1.0)
    with contextlib.suppress(TimeoutError):
        sock.recv(256)

    # Start a reader thread for event frames.
    events_received: list[tuple[int, bytes]] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            frame = recv_frame(sock, timeout=0.5)
            if frame is not None:
                events_received.append(frame)

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()

    # Stream the 16 channels interleaved, pacing at the UART rate.
    print(f"[demo] streaming {NUM_CHANNELS} channels to the firmware...")
    frames_sent = 0
    events_in_stream = 0
    start = time.monotonic()
    for i in range(n_samples):
        if time.monotonic() - start > args.duration:
            print(f"[demo] reached {args.duration}s wall duration, stopping")
            break
        for ch in range(NUM_CHANNELS):
            sample = float(waveforms[ch][i])
            frame = encode_sample_frame(ch, sample)
            sock.sendall(frame)
            frames_sent += 1
            # Publish any event frames we received back.
            while events_received:
                channel, payload = events_received.pop(0)
                events_in_stream += 1
                envelope = json.dumps(
                    {
                        "channel": channel,
                        "payload": payload.hex(),
                        "sim_clock_factor": clock.factor,
                        "t": time.time(),
                    }
                )
                if mqtt_client is not None:
                    mqtt_client.publish("mycelium/events", envelope)
                # SpikeFeatures: u8 count at 0, 3 pad, f32 amplitude at offset 4.
                amp = struct.unpack("<f", payload[4:8])[0]
                print(f"  [event] ch={channel} amp={amp:.3f}")
            time.sleep(0.002)  # pace: ~0.5ms per frame, ~2000 frames/s

    print(f"[demo] sent {frames_sent} sample frames in {time.monotonic() - start:.1f}s")

    # Flush remaining events.
    time.sleep(1.0)
    stop.set()
    reader_thread.join(timeout=2.0)

    # Count total events (the streaming loop already drained most of them).
    total_events = len(events_received)
    while events_received:
        channel, payload = events_received.pop(0)
        total_events += 1
        envelope = json.dumps(
            {
                "channel": channel,
                "payload": payload.hex(),
                "sim_clock_factor": clock.factor,
                "t": time.time(),
            }
        )
        if mqtt_client is not None:
            mqtt_client.publish("mycelium/events", envelope)

    print(f"[demo] total events received: {total_events + events_in_stream}")
    print(f"[demo] sim-clock: {clock.factor_label()} — never mistake for real time (ADR-006)")
    print("[demo] check Grafana at http://localhost:3000 for the live dashboard")

    sock.close()
    stop.set()
    renode.kill()
    renode.wait(timeout=3)
    if mqtt_client is not None:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    os.close(fd9)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
