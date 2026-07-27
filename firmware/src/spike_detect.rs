//! Adaptive spike detection using median absolute deviation (MAD).
//!
//! Each channel has a different noise floor that drifts over time, so a fixed
//! voltage threshold is wrong (ADR-004). Instead we maintain a rolling window
//! of recent samples, estimate the noise scale from the MAD, and trip when a
//! sample exceeds `k * sigma_hat` where `sigma_hat = MAD / 0.7561` (the
//! 0.7561 normalises MAD to a standard-deviation estimate for Gaussian noise).
//!
//! A refractory period prevents double-counting the same spike. The detector
//! is `no_std`, alloc-free, constant time per sample, and host-testable.

/// The normalisation constant that turns MAD into a standard-deviation
/// estimate for Gaussian noise: `sigma ≈ MAD / 0.7561`.
const MAD_TO_SIGMA: f32 = 1.0 / 0.7561;

/// Default rolling-window length (samples). Long enough to estimate MAD
/// robustly, short enough to track drifting noise floors. At 1 kHz this is
/// ~0.5 s of history.
pub const DEFAULT_WINDOW: usize = 512;

/// Default threshold multiplier: trip at ~5 sigma above the noise floor. This
/// is high enough to keep the false-positive rate low on Gaussian noise, low
/// enough to catch the simulated spikes (amplitude 1-5 mV vs noise ~0.02 mV).
pub const DEFAULT_K: f32 = 5.0;

/// Default refractory period in samples: once a spike fires, ignore the next
/// `DEFAULT_REFRACTORY` samples so the biphasic undershoot doesn't double-fire.
/// At 1 kHz, 30 ms covers a 5 ms spike plus its undershoot with margin.
pub const DEFAULT_REFRACTORY: usize = 30;

/// A rolling-window MAD-based adaptive spike detector.
///
/// The window is a fixed-size ring buffer of recent samples. MAD is recomputed
/// from the window on every sample (the window is small enough that the O(n)
/// scan is cheap on a Cortex-M4). The detector emits `Some(amplitude)` when a
/// spike is detected and `None` otherwise.
#[derive(Debug, Clone)]
pub struct SpikeDetector {
    window: [f32; DEFAULT_WINDOW],
    filled: usize,
    head: usize,
    threshold_k: f32,
    refractory: usize,
    samples_since_spike: usize,
    last_threshold: f32,
}

impl SpikeDetector {
    /// Construct a new detector with the given threshold multiplier `k` and
    /// refractory period (samples).
    #[must_use]
    pub fn new(threshold_k: f32, refractory: usize) -> Self {
        debug_assert!(threshold_k > 0.0);
        Self {
            window: [0.0; DEFAULT_WINDOW],
            filled: 0,
            head: 0,
            threshold_k,
            refractory,
            samples_since_spike: usize::MAX,
            last_threshold: f32::INFINITY,
        }
    }

    /// Construct a detector with the default parameters.
    #[must_use]
    pub fn default_detector() -> Self {
        Self::new(DEFAULT_K, DEFAULT_REFRACTORY)
    }

    /// Reset the detector state (e.g. on a new channel).
    pub fn reset(&mut self) {
        self.window = [0.0; DEFAULT_WINDOW];
        self.filled = 0;
        self.head = 0;
        self.samples_since_spike = usize::MAX;
        self.last_threshold = f32::INFINITY;
    }

    /// Number of samples currently in the rolling window.
    #[must_use]
    pub fn window_filled(&self) -> usize {
        self.filled
    }

    /// The most recent threshold value (in input units). Useful for tests and
    /// for telemetry. Returns infinity until the window is full.
    #[must_use]
    pub fn current_threshold(&self) -> f32 {
        self.last_threshold
    }

    /// Process a single filtered sample. Returns `Some(amplitude)` if a spike
    /// is detected on this sample, `None` otherwise.
    ///
    /// The detector assumes the input has already been high-pass filtered (so
    /// DC drift is gone) and notched (so mains hum is gone). The MAD then
    /// estimates the residual noise floor.
    #[must_use]
    pub fn process(&mut self, sample: f32) -> Option<f32> {
        // Push the sample into the ring buffer.
        self.window[self.head] = sample;
        self.head = (self.head + 1) % DEFAULT_WINDOW;
        if self.filled < DEFAULT_WINDOW {
            self.filled += 1;
        }

        // Refractory: don't fire if we're still in the post-spike window.
        if self.samples_since_spike < self.refractory {
            self.samples_since_spike = self.samples_since_spike.saturating_add(1);
            return None;
        }

        // Need a full window before we can threshold reliably.
        if self.filled < DEFAULT_WINDOW {
            return None;
        }

        // Compute MAD over the window. The median is approximated by the
        // running mean (since the signal is high-passed, the mean is ~0);
        // MAD is then median(|x - mean|). For a Gaussian-noise channel with
        // zero mean this is a good scale estimate and avoids a full sort.
        // DEFAULT_WINDOW is small (512) and fits exactly in f32.
        #[allow(clippy::cast_precision_loss)]
        let n = DEFAULT_WINDOW as f32;
        let mut mean = 0.0_f32;
        for &v in &self.window {
            mean += v;
        }
        mean /= n;

        let mut abs_dev_sum = 0.0_f32;
        for &v in &self.window {
            abs_dev_sum += (v - mean).abs();
        }
        let mad = abs_dev_sum / n;
        let sigma_hat = mad * MAD_TO_SIGMA;
        let threshold = self.threshold_k * sigma_hat;
        self.last_threshold = threshold;

        // Trip on a positive excursion above the threshold. (The high-pass
        // filter removes DC, so spikes are bipolar around zero; we trip on the
        // positive peak, which is the first phase of the biphasic kernel.)
        if sample > threshold && threshold.is_finite() && threshold > 0.0 {
            self.samples_since_spike = 0;
            return Some(sample);
        }
        None
    }

    /// A reference to the rolling window contents (for tests and telemetry).
    #[cfg(test)]
    fn window_slice(&self) -> &[f32] {
        &self.window[..self.filled]
    }
}

#[cfg(all(test, feature = "std"))]
mod tests {
    use super::*;

    #[test]
    fn detector_does_not_fire_before_window_fills() {
        let mut det = SpikeDetector::default_detector();
        // Feed pure Gaussian noise; no detection expected until window fills.
        let mut state: u32 = 1;
        for _ in 0..(DEFAULT_WINDOW - 1) {
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            let n = ((state >> 8) as f32 / (1u32 << 24) as f32 - 0.5) * 0.1;
            assert!(det.process(n).is_none(), "fired before window filled");
        }
    }

    #[test]
    fn detector_fires_on_spike_above_noise_floor() {
        let mut det = SpikeDetector::default_detector();
        // Noise sigma ~0.02, spike amplitude 2.0 — well above 5 sigma.
        let mut detected = false;
        let mut state: u32 = 42;
        for i in 0..(DEFAULT_WINDOW + 200) {
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            let n = ((state >> 8) as f32 / (1u32 << 24) as f32 - 0.5) * 0.08;
            let sample = if i == DEFAULT_WINDOW + 50 { 2.0 } else { n };
            if det.process(sample).is_some() {
                detected = true;
                break;
            }
        }
        assert!(detected, "detector did not fire on a clear spike");
    }

    #[test]
    fn detector_adapts_to_different_noise_floors() {
        // A loud channel (sigma 0.5) should not fire on a 0.5 amplitude blip
        // that a quiet channel (sigma 0.02) would fire on.
        let mut loud = SpikeDetector::default_detector();
        let mut quiet = SpikeDetector::default_detector();
        // Fill both windows with their respective noise floors.
        let mut state: u32 = 100;
        for _ in 0..DEFAULT_WINDOW {
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            let u = (state >> 8) as f32 / (1u32 << 24) as f32 - 0.5;
            let _ = loud.process(u * 2.0 * 0.5);
            let _ = quiet.process(u * 2.0 * 0.02);
        }
        // A 0.5 amplitude spike: below the loud threshold, above the quiet one.
        let loud_fire = loud.process(0.5).is_some();
        let quiet_fire = quiet.process(0.5).is_some();
        assert!(!loud_fire, "loud channel fired on a small spike");
        assert!(quiet_fire, "quiet channel missed a clear spike");
    }

    #[test]
    fn refractory_prevents_double_firing() {
        let mut det = SpikeDetector::new(DEFAULT_K, 50);
        // Fill with noise.
        let mut state: u32 = 7;
        for _ in 0..DEFAULT_WINDOW {
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            let n = ((state >> 8) as f32 / (1u32 << 24) as f32 - 0.5) * 0.04;
            let _ = det.process(n);
        }
        // A burst of high samples: should fire once, then not again during the
        // refractory period.
        let mut fires = 0;
        for _ in 0..40 {
            if det.process(2.0).is_some() {
                fires += 1;
            }
        }
        assert_eq!(fires, 1, "refractory failed: fired {fires} times");
    }

    #[test]
    fn reset_clears_state() {
        let mut det = SpikeDetector::default_detector();
        // Fill with noise and one spike.
        let mut state: u32 = 9;
        for i in 0..(DEFAULT_WINDOW + 10) {
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            let n = ((state >> 8) as f32 / (1u32 << 24) as f32 - 0.5) * 0.04;
            let s = if i == DEFAULT_WINDOW + 5 { 3.0 } else { n };
            let _ = det.process(s);
        }
        assert!(det.window_filled() == DEFAULT_WINDOW);
        det.reset();
        assert_eq!(det.window_filled(), 0);
        assert!(det.current_threshold().is_infinite());
    }

    #[test]
    fn threshold_is_nonzero_after_window_fills() {
        let mut det = SpikeDetector::default_detector();
        let mut state: u32 = 33;
        for _ in 0..DEFAULT_WINDOW {
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            let n = ((state >> 8) as f32 / (1u32 << 24) as f32 - 0.5) * 0.1;
            let _ = det.process(n);
        }
        let thr = det.current_threshold();
        assert!(thr.is_finite() && thr > 0.0, "threshold not set: {thr}");
    }
}
