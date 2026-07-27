//! On-MCU feature extraction for detected spikes (ADR-005).
//!
//! When the spike detector fires, the firmware records the amplitude and the
//! sample index. This module maintains a small per-channel rolling window of
//! recent detections and, on each new detection, computes a compact feature
//! vector (~20 scalar features) that gets serialised into an event frame and
//! sent over the UART.
//!
//! Only features cross the wire — never raw samples. That's the bandwidth
//! argument that justifies an MCU in the architecture at all (ADR-005).
//!
//! The extractor is `no_std`, alloc-free, and host-testable.

/// Number of recent detections retained for feature computation.
pub const HISTORY_LEN: usize = 32;
/// Number of amplitude histogram bins (log-spaced would need libm; we use
/// linear bins over a fixed range for `no_std` simplicity).
pub const HISTOGRAM_BINS: usize = 8;
/// Amplitude range covered by the histogram, in input units (mV). Anything
/// above is clamped into the top bin.
const HISTOGRAM_MAX: f32 = 10.0;

/// A per-channel spike feature extractor.
///
/// Holds a ring buffer of the last [`HISTORY_LEN`] detections (amplitude +
/// sample index) and computes features over them on each new detection.
#[derive(Debug, Clone)]
pub struct FeatureExtractor {
    amplitudes: [f32; HISTORY_LEN],
    timestamps: [u64; HISTORY_LEN],
    filled: usize,
    head: usize,
}

/// A compact feature vector computed from the recent spike history.
///
/// This is the on-wire format — it gets packed into a frame payload. The
/// fields are deliberately `f32`/`u8` and the struct is `#[repr(C)]` so the
/// byte layout is fixed and the ingest service can decode it.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SpikeFeatures {
    /// Number of spikes in the rolling window (capped at `HISTORY_LEN`).
    pub count: u8,
    /// Most recent spike amplitude (mV).
    pub amplitude: f32,
    /// Mean amplitude over the window (mV).
    pub amplitude_mean: f32,
    /// Std dev of amplitude over the window (mV).
    pub amplitude_std: f32,
    /// Min amplitude over the window (mV).
    pub amplitude_min: f32,
    /// Max amplitude over the window (mV).
    pub amplitude_max: f32,
    /// Mean inter-spike interval over the window (samples).
    pub isi_mean: f32,
    /// Std dev of ISI over the window (samples).
    pub isi_std: f32,
    /// Minimum ISI over the window (samples).
    pub isi_min: f32,
    /// Maximum ISI over the window (samples).
    pub isi_max: f32,
    /// Burst index: ratio of the long-window mean ISI to the short-window
    /// mean ISI. >1 means the recent rate is higher than the long-term average.
    pub burst_index: f32,
    /// Spike rate over the full window (Hz, requires sample rate at pack time).
    pub rate: f32,
    /// Amplitude histogram: 8 linear bins over `[0, HISTOGRAM_MAX]` mV.
    pub histogram: [u8; HISTOGRAM_BINS],
}

impl SpikeFeatures {
    /// An all-zero feature vector (returned when the window is empty).
    #[must_use]
    pub const fn zero() -> Self {
        Self {
            count: 0,
            amplitude: 0.0,
            amplitude_mean: 0.0,
            amplitude_std: 0.0,
            amplitude_min: 0.0,
            amplitude_max: 0.0,
            isi_mean: 0.0,
            isi_std: 0.0,
            isi_min: 0.0,
            isi_max: 0.0,
            burst_index: 0.0,
            rate: 0.0,
            histogram: [0; HISTOGRAM_BINS],
        }
    }
}

impl FeatureExtractor {
    /// Construct a new empty feature extractor.
    #[must_use]
    pub fn new() -> Self {
        Self {
            amplitudes: [0.0; HISTORY_LEN],
            timestamps: [0; HISTORY_LEN],
            filled: 0,
            head: 0,
        }
    }

    /// Record a new spike detection and return the freshly-computed features.
    ///
    /// `amplitude` is the detected spike amplitude (mV). `sample_index` is the
    /// monotonically-increasing sample counter for this channel. `sample_rate`
    /// is the ADC sample rate (Hz), used to convert ISI to a rate.
    #[must_use]
    pub fn record(&mut self, amplitude: f32, sample_index: u64, sample_rate: f32) -> SpikeFeatures {
        self.amplitudes[self.head] = amplitude;
        self.timestamps[self.head] = sample_index;
        self.head = (self.head + 1) % HISTORY_LEN;
        if self.filled < HISTORY_LEN {
            self.filled += 1;
        }
        self.compute(sample_rate)
    }

    /// Reset the extractor (e.g. on a new channel).
    pub fn reset(&mut self) {
        self.amplitudes = [0.0; HISTORY_LEN];
        self.timestamps = [0; HISTORY_LEN];
        self.filled = 0;
        self.head = 0;
    }

    /// Number of detections currently in the rolling window.
    #[must_use]
    pub fn len(&self) -> usize {
        self.filled
    }

    /// Whether the window is empty.
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.filled == 0
    }

    /// Iterate over the amplitudes in time order.
    fn amps_iter(&self) -> impl Iterator<Item = f32> + '_ {
        let n = self.filled;
        let head = self.head;
        let total = HISTORY_LEN;
        (0..n).map(move |i| {
            if n < total {
                self.amplitudes[i]
            } else {
                self.amplitudes[(head + i) % total]
            }
        })
    }

    /// Iterate over the timestamps in time order.
    fn times_iter(&self) -> impl Iterator<Item = u64> + '_ {
        let n = self.filled;
        let head = self.head;
        let total = HISTORY_LEN;
        (0..n).map(move |i| {
            if n < total {
                self.timestamps[i]
            } else {
                self.timestamps[(head + i) % total]
            }
        })
    }

    fn compute(&self, sample_rate: f32) -> SpikeFeatures {
        let n = self.filled;
        if n == 0 {
            return SpikeFeatures::zero();
        }
        let (amplitude, amplitude_mean, amplitude_std, amplitude_min, amplitude_max, histogram) =
            self.amplitude_stats();
        let (isi_mean, isi_std, isi_min, isi_max) = self.isi_stats(n);
        let burst_index = self.burst_index(n, isi_mean);
        let rate = self.rate(n, sample_rate);
        SpikeFeatures {
            count: u8::try_from(n).unwrap_or(u8::MAX),
            amplitude,
            amplitude_mean,
            amplitude_std,
            amplitude_min,
            amplitude_max,
            isi_mean,
            isi_std,
            isi_min,
            isi_max,
            burst_index,
            rate,
            histogram,
        }
    }

    #[allow(clippy::cast_precision_loss, clippy::cast_possible_truncation)]
    fn amplitude_stats(&self) -> (f32, f32, f32, f32, f32, [u8; HISTOGRAM_BINS]) {
        let mut sum = 0.0_f32;
        let mut sum_sq = 0.0_f32;
        let mut amin = f32::INFINITY;
        let mut amax = f32::NEG_INFINITY;
        let mut last = 0.0_f32;
        let mut histogram = [0_u8; HISTOGRAM_BINS];
        for a in self.amps_iter() {
            sum += a;
            sum_sq += a * a;
            if a < amin {
                amin = a;
            }
            if a > amax {
                amax = a;
            }
            last = a;
            // Amplitude is non-negative after the detector; the cast to usize
            // is sign-safe in practice. The clamp keeps the bin in range.
            #[allow(clippy::cast_sign_loss)]
            let bin = (((a / HISTOGRAM_MAX).clamp(0.0, 0.999) * HISTOGRAM_BINS as f32) as usize)
                .min(HISTOGRAM_BINS - 1);
            histogram[bin] = histogram[bin].saturating_add(1);
        }
        let n = self.filled as f32;
        let mean = sum / n;
        let variance = (sum_sq / n) - mean * mean;
        let std = if variance > 0.0 {
            libm::sqrtf(variance)
        } else {
            0.0
        };
        (last, mean, std, amin, amax, histogram)
    }

    #[allow(clippy::cast_precision_loss)]
    fn isi_stats(&self, n: usize) -> (f32, f32, f32, f32) {
        if n < 2 {
            return (0.0, 0.0, 0.0, 0.0);
        }
        let mut isi_sum = 0.0_f32;
        let mut isi_sum_sq = 0.0_f32;
        let mut isi_min_v = u64::MAX;
        let mut isi_max_v = 0_u64;
        let mut prev: Option<u64> = None;
        for t in self.times_iter() {
            if let Some(p) = prev {
                let isi = t.saturating_sub(p);
                let isi_f = isi as f32;
                isi_sum += isi_f;
                isi_sum_sq += isi_f * isi_f;
                if isi < isi_min_v {
                    isi_min_v = isi;
                }
                if isi > isi_max_v {
                    isi_max_v = isi;
                }
            }
            prev = Some(t);
        }
        let m = (n - 1) as f32;
        let mean = isi_sum / m;
        let var = (isi_sum_sq / m) - mean * mean;
        let std = if var > 0.0 { libm::sqrtf(var) } else { 0.0 };
        (mean, std, isi_min_v as f32, isi_max_v as f32)
    }

    #[allow(clippy::cast_precision_loss)]
    fn burst_index(&self, n: usize, isi_mean: f32) -> f32 {
        if n < 6 || isi_mean <= 0.0 {
            return 1.0;
        }
        let short_start = n.saturating_sub(5);
        let mut short_sum = 0.0_f32;
        let mut short_count = 0.0_f32;
        let mut prev: Option<u64> = None;
        for (idx, t) in self.times_iter().enumerate() {
            if idx >= short_start {
                if let Some(p) = prev {
                    short_sum += t.saturating_sub(p) as f32;
                    short_count += 1.0;
                }
            }
            prev = Some(t);
        }
        if short_count > 0.0 && short_sum > 0.0 {
            isi_mean / (short_sum / short_count)
        } else {
            1.0
        }
    }

    #[allow(clippy::cast_precision_loss)]
    fn rate(&self, n: usize, sample_rate: f32) -> f32 {
        if n < 2 || sample_rate <= 0.0 {
            return 0.0;
        }
        let mut first: Option<u64> = None;
        let mut last = 0_u64;
        for t in self.times_iter() {
            if first.is_none() {
                first = Some(t);
            }
            last = t;
        }
        let span = last.saturating_sub(first.unwrap_or(0));
        let span_s = span as f32 / sample_rate;
        if span_s > 0.0 {
            (n - 1) as f32 / span_s
        } else {
            0.0
        }
    }
}

impl Default for FeatureExtractor {
    fn default() -> Self {
        Self::new()
    }
}

/// Pack a [`SpikeFeatures`] struct into a byte slice for the UART frame
/// payload. The layout is `#[repr(C)]` so the bytes are the struct's raw
/// memory image; the ingest service decodes with the same layout.
///
/// Returns the number of bytes written. The buffer must be at least
/// `size_of::<SpikeFeatures>()` bytes.
#[must_use]
pub fn pack_features(features: &SpikeFeatures, out: &mut [u8]) -> Option<usize> {
    let n = core::mem::size_of::<SpikeFeatures>();
    if out.len() < n {
        return None;
    }
    let src = core::ptr::from_ref(features).cast::<u8>();
    // Safety: copying the bytes of a #[repr(C)] struct with no padding holes
    // into a destination slice of sufficient length. The source is a valid
    // reference for the duration of the copy.
    unsafe {
        core::ptr::copy_nonoverlapping(src, out.as_mut_ptr(), n);
    }
    Some(n)
}

/// Unpack a [`SpikeFeatures`] from a byte slice (host-side / ingest use).
///
/// This is the inverse of [`pack_features`]. Available with the `std` feature
/// so the ingest service can decode event frames.
#[cfg(feature = "std")]
#[must_use]
pub fn unpack_features(buf: &[u8]) -> Option<SpikeFeatures> {
    let n = core::mem::size_of::<SpikeFeatures>();
    if buf.len() < n {
        return None;
    }
    let mut features = SpikeFeatures::zero();
    let dst = core::ptr::from_mut(&mut features).cast::<u8>();
    // Safety: same layout contract as pack_features.
    unsafe {
        core::ptr::copy_nonoverlapping(buf.as_ptr(), dst, n);
    }
    Some(features)
}

#[cfg(all(test, feature = "std"))]
mod tests {
    use super::*;

    #[test]
    fn empty_extractor_returns_zero_features() {
        let ex = FeatureExtractor::new();
        let f = ex.compute(1000.0);
        assert_eq!(f.count, 0);
        assert_eq!(f.amplitude, 0.0);
        assert_eq!(f.histogram, [0; HISTOGRAM_BINS]);
    }

    #[test]
    fn single_detection_has_no_isi() {
        let mut ex = FeatureExtractor::new();
        let f = ex.record(2.5, 100, 1000.0);
        assert_eq!(f.count, 1);
        assert!((f.amplitude - 2.5).abs() < 1e-6);
        assert!((f.amplitude_mean - 2.5).abs() < 1e-6);
        assert_eq!(f.isi_mean, 0.0);
        assert_eq!(f.rate, 0.0);
    }

    #[test]
    fn two_detections_compute_isi() {
        let mut ex = FeatureExtractor::new();
        let _ = ex.record(2.0, 100, 1000.0);
        let f = ex.record(3.0, 300, 1000.0);
        assert_eq!(f.count, 2);
        assert!(
            (f.isi_mean - 200.0).abs() < 1e-3,
            "isi_mean wrong: {}",
            f.isi_mean
        );
        assert!((f.isi_min - 200.0).abs() < 1e-3);
        assert!((f.isi_max - 200.0).abs() < 1e-3);
        assert!((f.rate - 5.0).abs() < 1e-3, "rate wrong: {}", f.rate);
    }

    #[test]
    fn amplitude_stats_over_window() {
        let mut ex = FeatureExtractor::new();
        for &a in &[1.0_f32, 2.0, 3.0, 4.0, 5.0] {
            let _ = ex.record(a, 0, 1000.0);
        }
        let f = ex.compute(1000.0);
        assert!((f.amplitude_mean - 3.0).abs() < 1e-5);
        assert!((f.amplitude_min - 1.0).abs() < 1e-5);
        assert!((f.amplitude_max - 5.0).abs() < 1e-5);
        assert!(f.amplitude_std > 0.0);
    }

    #[test]
    fn histogram_buckets_amplitudes() {
        let mut ex = FeatureExtractor::new();
        // HISTOGRAM_MAX = 10, 8 bins -> bin width 1.25.
        // 0.5 -> bin 0, 2.0 -> bin 1, 5.0 -> bin 4, 9.0 -> bin 7.
        let _ = ex.record(0.5, 0, 1000.0);
        let _ = ex.record(2.0, 1, 1000.0);
        let _ = ex.record(5.0, 2, 1000.0);
        let _ = ex.record(9.0, 3, 1000.0);
        let f = ex.compute(1000.0);
        assert_eq!(f.histogram[0], 1);
        assert_eq!(f.histogram[1], 1);
        assert_eq!(f.histogram[4], 1);
        assert_eq!(f.histogram[7], 1);
        assert_eq!(f.histogram.iter().sum::<u8>(), 4);
    }

    #[test]
    fn window_caps_at_history_len() {
        let mut ex = FeatureExtractor::new();
        for i in 0..(HISTORY_LEN + 10) {
            let _ = ex.record(1.0, i as u64, 1000.0);
        }
        let f = ex.compute(1000.0);
        assert_eq!(f.count, HISTORY_LEN as u8);
    }

    #[test]
    fn burst_index_above_one_for_recent_burst() {
        // A long quiet period followed by closely-spaced spikes should give
        // a burst index > 1 (recent rate higher than long-term average).
        let mut ex = FeatureExtractor::new();
        // Long ISIs.
        for i in 0u64..20 {
            let _ = ex.record(1.0, i * 1000, 1000.0);
        }
        // Short ISIs at the end.
        for j in 0u64..10 {
            let _ = ex.record(1.0, 20_000 + j * 10, 1000.0);
        }
        let f = ex.compute(1000.0);
        assert!(
            f.burst_index > 1.0,
            "burst index should be >1 for a burst: {}",
            f.burst_index
        );
    }

    #[test]
    fn pack_unpack_round_trip() {
        let features = SpikeFeatures {
            count: 5,
            amplitude: 2.5,
            amplitude_mean: 2.0,
            amplitude_std: 0.5,
            amplitude_min: 1.0,
            amplitude_max: 3.0,
            isi_mean: 200.0,
            isi_std: 50.0,
            isi_min: 100.0,
            isi_max: 300.0,
            burst_index: 1.5,
            rate: 5.0,
            histogram: [1, 2, 3, 0, 0, 0, 0, 1],
        };
        let mut buf = [0u8; 256];
        let n = pack_features(&features, &mut buf).expect("packs");
        let decoded = unpack_features(&buf[..n]).expect("unpacks");
        assert_eq!(features, decoded);
    }

    #[test]
    fn pack_rejects_oversize_features() {
        let features = SpikeFeatures {
            count: 1,
            amplitude: 1.0,
            amplitude_mean: 1.0,
            amplitude_std: 0.0,
            amplitude_min: 1.0,
            amplitude_max: 1.0,
            isi_mean: 0.0,
            isi_std: 0.0,
            isi_min: 0.0,
            isi_max: 0.0,
            burst_index: 1.0,
            rate: 0.0,
            histogram: [1, 0, 0, 0, 0, 0, 0, 0],
        };
        let mut tiny = [0u8; 4];
        assert!(pack_features(&features, &mut tiny).is_none());
    }

    #[test]
    fn reset_clears_history() {
        let mut ex = FeatureExtractor::new();
        let _ = ex.record(2.0, 100, 1000.0);
        let _ = ex.record(3.0, 200, 1000.0);
        assert_eq!(ex.len(), 2);
        ex.reset();
        assert!(ex.is_empty());
        let f = ex.compute(1000.0);
        assert_eq!(f.count, 0);
    }
}
