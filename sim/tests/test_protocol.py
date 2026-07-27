"""Tests for the sim-side protocol helpers."""

from __future__ import annotations

from sim.protocol import FRAME_EOF, FRAME_SOF, decode_frame


def test_decode_valid_frame() -> None:
    buf = bytes([FRAME_SOF, 3, 2, 0xAB, 0xCD, FRAME_EOF])
    result = decode_frame(buf)
    assert result is not None
    (channel, payload), consumed = result
    assert channel == 3
    assert payload == b"\xab\xcd"
    assert consumed == len(buf)


def test_decode_partial_frame() -> None:
    buf = bytes([FRAME_SOF, 0, 5, 0x01])  # claims 5 payload bytes, only 1
    assert decode_frame(buf) is None


def test_decode_bad_sof() -> None:
    buf = bytes([0x00, 0, 0, FRAME_EOF])
    assert decode_frame(buf) is None


def test_decode_bad_eof() -> None:
    buf = bytes([FRAME_SOF, 1, 1, 0xAA, 0x00])  # EOF byte wrong
    assert decode_frame(buf) is None


def test_decode_empty_payload() -> None:
    buf = bytes([FRAME_SOF, 5, 0, FRAME_EOF])
    result = decode_frame(buf)
    assert result is not None
    (channel, payload), consumed = result
    assert channel == 5
    assert payload == b""
    assert consumed == 4
