//! Wire framing for the virtual UART between the simulator and the firmware,
//! and between the firmware and the ingest service.
//!
//! Frames carry features, never raw samples (ADR-005). The on-MCU side is
//! `no_std` and alloc-free, so payloads live in a fixed-size byte array. The
//! `std` feature adds `Vec`-based convenience helpers for host tests and the
//! ingest service.

/// Start-of-frame marker. Picked to be unlikely in arbitrary payload bytes.
pub const SOF: u8 = 0xA5;
/// End-of-frame marker.
pub const EOF: u8 = 0x5A;
/// Maximum payload length in bytes. Features-only frames are short.
pub const MAX_PAYLOAD: usize = 64;

/// A fixed-size payload buffer used in `no_std` contexts.
pub type PayloadBuf = [u8; MAX_PAYLOAD];

/// A single framed message with a fixed-size payload.
///
/// On-MCU code constructs this without allocation; host code can convert to/from
/// `Vec<u8>` via the `std` feature helpers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Frame {
    /// Channel index, 0..16.
    pub channel: u8,
    /// Number of valid bytes in `payload`.
    pub len: u8,
    /// Payload bytes (only `len` are valid).
    pub payload: PayloadBuf,
}

impl Frame {
    /// Construct an empty frame for a given channel.
    #[must_use]
    pub fn empty(channel: u8) -> Self {
        Self {
            channel,
            len: 0,
            payload: [0; MAX_PAYLOAD],
        }
    }

    /// Construct a frame from a slice, copying into the fixed buffer.
    ///
    /// Returns `None` if the slice is longer than [`MAX_PAYLOAD`].
    #[must_use]
    pub fn from_slice(channel: u8, payload: &[u8]) -> Option<Self> {
        if payload.len() > MAX_PAYLOAD {
            return None;
        }
        let len = u8::try_from(payload.len()).ok()?;
        let mut buf = [0u8; MAX_PAYLOAD];
        buf[..payload.len()].copy_from_slice(payload);
        Some(Self {
            channel,
            len,
            payload: buf,
        })
    }

    /// View the valid payload bytes.
    #[must_use]
    pub fn payload_bytes(&self) -> &[u8] {
        &self.payload[..usize::from(self.len)]
    }

    /// Serialise into the wire format `[SOF, channel, len, payload..., EOF]`.
    ///
    /// Writes into `out` and returns the number of bytes written, or `None` if
    /// `out` is too small.
    #[must_use]
    pub fn encode_into(&self, out: &mut [u8]) -> Option<usize> {
        let need = 3 + usize::from(self.len) + 1;
        if out.len() < need {
            return None;
        }
        out[0] = SOF;
        out[1] = self.channel;
        out[2] = self.len;
        out[3..3 + usize::from(self.len)].copy_from_slice(self.payload_bytes());
        out[3 + usize::from(self.len)] = EOF;
        Some(need)
    }

    /// Decode one frame from a buffer. Returns the frame and the number of bytes
    /// consumed, or `None` if the buffer doesn't contain a complete valid frame.
    #[must_use]
    pub fn decode(buf: &[u8]) -> Option<(Frame, usize)> {
        if buf.len() < 4 || buf[0] != SOF {
            return None;
        }
        let len = usize::from(buf[2]);
        if buf.len() < 3 + len + 1 || buf[3 + len] != EOF {
            return None;
        }
        Some((Frame::from_slice(buf[1], &buf[3..3 + len])?, 3 + len + 1))
    }
}

/// A streaming frame decoder for byte-at-a-time input (e.g. from a UART RX
/// poll loop). Feeding bytes one at a time produces complete frames when the
/// EOF marker arrives. Alloc-free: state is a small fixed buffer.
#[derive(Debug, Clone, Copy)]
pub struct FrameDecoder {
    state: DecodeState,
    channel: u8,
    len: u8,
    idx: u8,
    payload: PayloadBuf,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum DecodeState {
    Idle,
    GotSof,
    GotChannel,
    InPayload,
}

impl Default for FrameDecoder {
    fn default() -> Self {
        Self::new()
    }
}

impl FrameDecoder {
    /// Construct a new decoder ready to receive bytes.
    #[must_use]
    pub const fn new() -> Self {
        Self {
            state: DecodeState::Idle,
            channel: 0,
            len: 0,
            idx: 0,
            payload: [0; MAX_PAYLOAD],
        }
    }

    /// Feed one byte. Returns `Some(Frame)` when a complete, valid frame has
    /// arrived; `None` while still accumulating or after a framing error reset.
    #[must_use]
    pub fn feed(&mut self, byte: u8) -> Option<Frame> {
        match self.state {
            DecodeState::Idle => {
                if byte == SOF {
                    self.state = DecodeState::GotSof;
                }
                None
            }
            DecodeState::GotSof => {
                self.channel = byte;
                self.state = DecodeState::GotChannel;
                None
            }
            DecodeState::GotChannel => {
                self.len = byte;
                self.idx = 0;
                if byte == 0 {
                    // Empty payload: next byte must be EOF.
                    self.state = DecodeState::InPayload;
                } else {
                    self.state = DecodeState::InPayload;
                }
                None
            }
            DecodeState::InPayload => {
                if usize::from(self.idx) < usize::from(self.len) {
                    self.payload[usize::from(self.idx)] = byte;
                    self.idx = self.idx.saturating_add(1);
                } else if byte == EOF {
                    // Complete frame: copy out and reset.
                    let frame =
                        Frame::from_slice(self.channel, &self.payload[..usize::from(self.len)]);
                    *self = Self::new();
                    return frame;
                } else {
                    // Framing error: reset.
                    *self = Self::new();
                }
                None
            }
        }
    }

    /// Reset the decoder to the idle state, discarding any partial frame.
    pub fn reset(&mut self) {
        *self = Self::new();
    }
}

#[cfg(all(test, feature = "std"))]
mod tests {
    use super::*;

    #[test]
    fn round_trip_small_payload() {
        let f = Frame::from_slice(7, &[1, 2, 3]).expect("small payload fits");
        let mut out = [0u8; 16];
        let n = f.encode_into(&mut out).expect("encodes");
        let (g, used) = Frame::decode(&out[..n]).expect("round-trips");
        assert_eq!(f, g);
        assert_eq!(used, n);
    }

    #[test]
    fn oversize_payload_rejected() {
        assert!(Frame::from_slice(0, &[0; MAX_PAYLOAD + 1]).is_none());
    }

    #[test]
    fn partial_buffer_rejected() {
        let bytes = [SOF, 1, 2, 0xDE]; // claims 2 payload bytes, only has 1
        assert!(Frame::decode(&bytes).is_none());
    }

    #[test]
    fn bad_eof_rejected() {
        let mut bytes = [SOF, 1, 1, 0xAB, 0x00]; // EOF byte wrong
        let _ = &mut bytes;
        assert!(Frame::decode(&bytes).is_none());
    }

    #[test]
    fn decoder_assembles_frame_byte_by_byte() {
        let mut d = FrameDecoder::new();
        // SOF, channel=5, len=3, payload [9,9,9], EOF
        let stream = [SOF, 5, 3, 9, 9, 9, EOF];
        let mut got: Option<Frame> = None;
        for (i, b) in stream.iter().enumerate() {
            got = d.feed(*b);
            if i < stream.len() - 1 {
                assert!(got.is_none(), "unexpected early frame at byte {i}");
            }
        }
        let f = got.expect("final byte yields a frame");
        assert_eq!(f.channel, 5);
        assert_eq!(f.len, 3);
        assert_eq!(f.payload_bytes(), &[9, 9, 9]);
    }

    #[test]
    fn decoder_resets_on_garbage_between_frames() {
        let mut d = FrameDecoder::new();
        // Garbage then a valid frame.
        for b in [0x00, 0x11, 0x22] {
            assert!(d.feed(b).is_none());
        }
        let stream = [SOF, 2, 1, 0xAB, EOF];
        let mut got: Option<Frame> = None;
        for b in stream {
            got = d.feed(b);
        }
        let f = got.expect("frame after garbage");
        assert_eq!(f.channel, 2);
        assert_eq!(f.payload_bytes(), &[0xAB]);
    }

    #[test]
    fn decoder_handles_empty_payload() {
        let mut d = FrameDecoder::new();
        assert!(d.feed(SOF).is_none());
        assert!(d.feed(0).is_none());
        assert!(d.feed(0).is_none()); // len=0
        let f = d.feed(EOF).expect("empty frame completes");
        assert_eq!(f.len, 0);
        assert_eq!(f.channel, 0);
    }
}
