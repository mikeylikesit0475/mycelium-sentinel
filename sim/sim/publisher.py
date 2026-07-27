"""MQTT publisher for firmware event frames.

Reads event frames from the firmware's UART output (via the virtual UART
bridge socket) and publishes them to MQTT as JSON envelopes so the ingest
service can decode and store them.

The envelope format is:
    {"channel": <int>, "payload": "<hex bytes of SpikeFeatures>"}

Sprint 1.6: MQTT publish. The sim-clock factor is included in the envelope
so the dashboard never mistakes accelerated time for real time (ADR-006).
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time

import paho.mqtt.client as mqtt

from sim.protocol import decode_frame

logger = logging.getLogger("sim.publisher")

MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "mycelium/events")
UART_HOST = os.environ.get("UART_HOST", "127.0.0.1")
UART_PORT = int(os.environ.get("UART_PORT", "34568"))
SIM_CLOCK_FACTOR = float(os.environ.get("SIM_CLOCK_FACTOR", "60.0"))


class UartToMqttBridge:
    """Bridges firmware UART event frames to MQTT envelopes.

    Connects to the Renode UART socket terminal, reads frames, and publishes
    each as a JSON envelope. Runs a background thread for the socket read
    loop.
    """

    def __init__(
        self,
        mqtt_host: str = MQTT_HOST,
        mqtt_port: int = MQTT_PORT,
        uart_host: str = UART_HOST,
        uart_port: int = UART_PORT,
        topic: str = MQTT_TOPIC,
        sim_clock_factor: float = SIM_CLOCK_FACTOR,
    ) -> None:
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.uart_host = uart_host
        self.uart_port = uart_port
        self.topic = topic
        self.sim_clock_factor = sim_clock_factor
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._mqtt: mqtt.Client | None = None
        self.published: list[dict] = []  # for tests

    def _connect_mqtt(self) -> mqtt.Client:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.connect(self.mqtt_host, self.mqtt_port, 60)
        client.loop_start()
        self._mqtt = client
        return client

    def _run(self) -> None:
        sock: socket.socket | None = None
        mqtt_client: mqtt.Client | None = None
        buf = bytearray()
        while not self._stop.is_set():
            if sock is None:
                try:
                    sock = socket.create_connection((self.uart_host, self.uart_port), timeout=5)
                    sock.settimeout(0.5)
                except OSError:
                    time.sleep(1.0)
                    continue
            if mqtt_client is None:
                try:
                    mqtt_client = self._connect_mqtt()
                except OSError:
                    time.sleep(1.0)
                    continue
            try:
                data = sock.recv(256)
                if not data:
                    sock = None
                    continue
                buf.extend(data)
                # Drain any complete frames from the buffer.
                while True:
                    frame, consumed = decode_frame(bytes(buf))
                    if frame is None:
                        break
                    channel, payload = frame
                    envelope = {
                        "channel": channel,
                        "payload": payload.hex(),
                        "sim_clock_factor": self.sim_clock_factor,
                        "t": time.time(),
                    }
                    mqtt_client.publish(self.topic, json.dumps(envelope))
                    self.published.append(envelope)
                    del buf[:consumed]
            except TimeoutError:
                continue
            except OSError:
                sock = None
                continue
        if sock is not None:
            sock.close()
        if mqtt_client is not None:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
