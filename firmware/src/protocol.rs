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
}
