"""Wire protocol helpers shared between the sim publisher and the ingest consumer.

The frame format matches firmware/src/protocol.rs:
    [SOF=0xA5, channel, len, payload..., EOF=0x5A]
"""

from __future__ import annotations

FRAME_SOF = 0xA5
FRAME_EOF = 0x5A


def decode_frame(buf: bytes) -> tuple[tuple[int, bytes], int] | None:
    """Decode one frame from a buffer.

    Returns ((channel, payload), bytes_consumed) or None if the buffer doesn't
    contain a complete valid frame.
    """
    if len(buf) < 4 or buf[0] != FRAME_SOF:
        return None
    n = buf[2]
    if len(buf) < 3 + n + 1 or buf[3 + n] != FRAME_EOF:
        return None
    channel = buf[1]
    payload = bytes(buf[3 : 3 + n])
    return (channel, payload), 3 + n + 1
