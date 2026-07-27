"""Tests for the ingest MQTT consumer.

Sprint 1.6: the consumer decodes firmware event frames and stores them. Tests
cover the decode path and the on_message handler with a mock MQTT message.
"""

from __future__ import annotations

import json
import struct

from ingest.consumer import FEATURES_FMT, IngestConsumer, decode_features


def _make_features_payload(amplitude: float = 3.0, count: int = 1) -> bytes:
    # Pack a SpikeFeatures struct matching the #[repr(C)] layout.
    # FEATURES_FMT = "<B3x11f8B" — the 3x is implicit padding, no values passed.
    fields = (
        count,  # u8 count
        # 3 bytes padding (implicit in the format string)
        amplitude,  # amplitude
        amplitude,  # amplitude_mean
        0.1,  # amplitude_std
        amplitude,  # amplitude_min
        amplitude,  # amplitude_max
        100.0,  # isi_mean
        20.0,  # isi_std
        80.0,  # isi_min
        120.0,  # isi_max
        1.2,  # burst_index
        5.0,  # rate
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        1,  # histogram [u8; 8]
    )
    return struct.pack(FEATURES_FMT, *fields)


def test_decode_features_valid() -> None:
    payload = _make_features_payload(amplitude=2.5, count=3)
    event = decode_features(5, payload)
    assert event is not None
    assert event.channel == 5
    assert event.count == 3
    assert abs(event.amplitude - 2.5) < 1e-5
    assert abs(event.rate - 5.0) < 1e-5
    assert event.histogram == [1, 0, 0, 0, 0, 0, 0, 1]


def test_decode_features_too_short() -> None:
    assert decode_features(0, b"\x00\x00") is None


def test_consumer_on_message_decodes_envelope() -> None:
    consumer = IngestConsumer()
    payload = _make_features_payload(amplitude=4.0, count=2)
    envelope = json.dumps({"channel": 7, "payload": payload.hex()}).encode("utf-8")

    class FakeMsg:
        payload = envelope

    consumer.on_message(None, None, FakeMsg())  # type: ignore[arg-type]
    assert len(consumer.events) == 1
    assert consumer.events[0].channel == 7
    assert abs(consumer.events[0].amplitude - 4.0) < 1e-5


def test_consumer_on_message_bad_envelope_ignored() -> None:
    consumer = IngestConsumer()

    class FakeMsg:
        payload = b"not json"

    consumer.on_message(None, None, FakeMsg())  # type: ignore[arg-type]
    assert len(consumer.events) == 0


def test_consumer_event_dicts_serialise() -> None:
    consumer = IngestConsumer()
    payload = _make_features_payload()
    envelope = json.dumps({"channel": 0, "payload": payload.hex()}).encode("utf-8")

    class FakeMsg:
        payload = envelope

    consumer.on_message(None, None, FakeMsg())  # type: ignore[arg-type]
    dicts = consumer.event_dicts()
    assert len(dicts) == 1
    assert "channel" in dicts[0]
    assert "sim_clock_factor" in dicts[0]
