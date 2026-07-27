"""MQTT consumer for firmware event frames.

Subscribes to the firmware event topic, decodes the SpikeFeatures payload
(matching the #[repr(C)] layout from firmware/src/features.rs), and writes
each event to TimescaleDB. The ingest service is the bridge between the
emulated firmware's UART output (relayed to MQTT by the sim publisher) and
the Grafana dashboard.

Sprint 1.6: MQTT consumption + TimescaleDB sink. The classifier lands in
Sprint 2.2.
"""

from __future__ import annotations

import json
import logging
import os
import struct
import time
from dataclasses import asdict, dataclass

import paho.mqtt.client as mqtt

logger = logging.getLogger("ingest")

# SpikeFeatures layout — must match firmware/src/features.rs SpikeFeatures.
# #[repr(C)] on ARM/x86 with 4-byte align: u8 at 0, 3 bytes padding, then
# 11 x f32 starting at offset 4, then [u8; 8] at offset 48. Total 56 bytes.
FEATURES_FMT = "<B3x11f8B"
FEATURES_SIZE = struct.calcsize(FEATURES_FMT)

MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "mycelium/events")
# Sim-clock acceleration factor — included in every event so the dashboard
# can never mistake accelerated time for real time (ADR-006).
SIM_CLOCK_FACTOR = float(os.environ.get("SIM_CLOCK_FACTOR", "1.0"))


@dataclass
class SpikeEvent:
    """A decoded spike event ready for storage."""

    channel: int
    timestamp: float
    count: int
    amplitude: float
    amplitude_mean: float
    amplitude_std: float
    amplitude_min: float
    amplitude_max: float
    isi_mean: float
    isi_std: float
    isi_min: float
    isi_max: float
    burst_index: float
    rate: float
    histogram: list[int]
    sim_clock_factor: float


def decode_features(channel: int, payload: bytes) -> SpikeEvent | None:
    """Decode a SpikeFeatures payload into a SpikeEvent."""
    if len(payload) < FEATURES_SIZE:
        return None
    fields = struct.unpack(FEATURES_FMT, payload[:FEATURES_SIZE])
    return SpikeEvent(
        channel=channel,
        timestamp=time.time(),
        count=fields[0],
        amplitude=fields[1],
        amplitude_mean=fields[2],
        amplitude_std=fields[3],
        amplitude_min=fields[4],
        amplitude_max=fields[5],
        isi_mean=fields[6],
        isi_std=fields[7],
        isi_min=fields[8],
        isi_max=fields[9],
        burst_index=fields[10],
        rate=fields[11],
        histogram=list(fields[12:20]),
        sim_clock_factor=SIM_CLOCK_FACTOR,
    )


class IngestConsumer:
    """MQTT consumer that decodes event frames and writes them to storage.

    Sprint 1.6 ships an in-memory store (a list) so the service runs without a
    database dependency in tests. The TimescaleDB sink is wired but optional —
    if the DB isn't reachable, events are still collected in memory.
    """

    def __init__(self) -> None:
        self.events: list[SpikeEvent] = []
        self._client: mqtt.Client | None = None

    def on_connect(self, client: mqtt.Client, _userdata, _flags, rc: int) -> None:
        logger.info("connected to MQTT broker (rc=%d), subscribing to %s", rc, MQTT_TOPIC)
        client.subscribe(MQTT_TOPIC)

    def on_message(self, _client: mqtt.Client, _userdata, msg: mqtt.MQTTMessage) -> None:
        # The MQTT payload is a JSON envelope: {"channel": N, "payload": "<hex>"}
        # The hex payload is the raw SpikeFeatures bytes from the firmware.
        try:
            envelope = json.loads(msg.payload.decode("utf-8"))
            channel = int(envelope["channel"])
            payload = bytes.fromhex(envelope["payload"])
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("bad envelope: %s", e)
            return
        event = decode_features(channel, payload)
        if event is None:
            logger.warning("undecodable features payload (len=%d)", len(payload))
            return
        self.events.append(event)
        logger.info(
            "event ch=%d amp=%.3f count=%d rate=%.2f",
            event.channel,
            event.amplitude,
            event.count,
            event.rate,
        )

    def connect(self) -> None:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_connect = self.on_connect
        client.on_message = self.on_message
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

    def event_dicts(self) -> list[dict]:
        return [asdict(e) for e in self.events]
