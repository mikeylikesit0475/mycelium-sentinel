//! Digital signal processing blocks for the Mycelium Sentinel firmware.
//!
//! Host-testable and on-target: the same code paths run under `cargo test` with
//! the `std` feature and inside the emulated MCU. (CLAUDE.md: "Don't let a block
//! become emulator-only.")
//!
//! Sprint 1.2 ships the real front-end filters:
//! - [`HighPassIir`] — first-order IIR high-pass for electrode DC drift removal,
//! - [`Notch50Hz`] — second-order IIR band-stop at 50 Hz for mains hum removal.
//!
//! Both are sample-in/sample-out stages implementing [`DspStage`], use no
//! allocation and run in constant time per sample. MAD-based spike detection
//! (Sprint 1.3) and feature extraction (Sprint 1.4) build on top of these.

/// A processing stage that takes one sample in and produces one sample out.
pub trait DspStage {
    /// Process a single sample, mutating internal state as needed.
    fn process(&mut self, sample: f32) -> f32;
}

/// Pass-through stage. Useful for tests and as a baseline in the chain.
pub struct Identity;

impl DspStage for Identity {
    #[inline]
    fn process(&mut self, sample: f32) -> f32 {
        sample
    }
}

/// First-order IIR high-pass filter for electrode DC drift removal.
///
/// Transfer function: `H(z) = (1 - z^-1) / (1 - α z^-1)` where
/// `α = exp(-2π · fc / fs)`. The cutoff `fc` is chosen well below the
/// spike band so spike shapes are preserved while slow electrode drift is
/// removed.
///
/// Constant time per sample, no allocation, no_std-safe.
#[derive(Debug, Clone)]
pub struct HighPassIir {
    alpha: f32,
    prev_input: f32,
    prev_output: f32,
}

impl HighPassIir {
    /// Construct a new high-pass filter.
    ///
    /// `cutoff_hz` is the -3 dB cutoff frequency; `sample_rate_hz` is the
    /// sampling rate. Both must be positive and `cutoff_hz` must be below
    /// the Nyquist frequency (`sample_rate_hz / 2`).
    #[must_use]
    pub fn new(cutoff_hz: f32, sample_rate_hz: f32) -> Self {
        debug_assert!(cutoff_hz > 0.0 && sample_rate_hz > 0.0);
        debug_assert!(cutoff_hz < sample_rate_hz / 2.0);
        // libm provides expf for no_std; on host it dispatches to libm too.
        let alpha = libm::expf(-core::f32::consts::TAU * cutoff_hz / sample_rate_hz);
        Self {
            alpha,
            prev_input: 0.0,
            prev_output: 0.0,
        }
    }

    /// Reset the filter state (e.g. on a new channel).
    pub fn reset(&mut self) {
        self.prev_input = 0.0;
        self.prev_output = 0.0;
    }
}

impl DspStage for HighPassIir {
    #[inline]
    fn process(&mut self, sample: f32) -> f32 {
        // y[n] = α (y[n-1] + x[n] - x[n-1])
        let out = self.alpha * (self.prev_output + sample - self.prev_input);
        self.prev_input = sample;
        self.prev_output = out;
        out
    }
}

/// Second-order IIR band-stop (notch) filter at 50 Hz for mains hum removal.
///
/// Implements the standard twin-T notch transfer function with coefficients
/// precomputed at construction from the target frequency, sample rate and a
/// quality factor `Q` controlling the notch width.
///
/// Constant time per sample, no allocation, no_std-safe.
#[derive(Debug, Clone)]
pub struct Notch50Hz {
    // Difference-equation coefficients: y[n] = b0 x[n] + b1 x[n-1] + b2 x[n-2]
    //                                       - a1 y[n-1] - a2 y[n-2]
    b0: f32,
    b1: f32,
    b2: f32,
    a1: f32,
    a2: f32,
    prev_x: [f32; 2],
    prev_y: [f32; 2],
}

impl Notch50Hz {
    /// Construct a 50 Hz notch filter for the given sample rate.
    ///
    /// `quality_factor` controls the notch width: higher Q is a narrower
    /// notch. A value around 35 gives a tight notch at 50 Hz that leaves the
    /// spike band untouched.
    #[must_use]
    pub fn new(sample_rate_hz: f32, quality_factor: f32) -> Self {
        debug_assert!(sample_rate_hz > 0.0);
        debug_assert!(quality_factor > 0.0);
        let f0 = 50.0_f32;
        let w0 = core::f32::consts::TAU * f0 / sample_rate_hz;
        let cos_w0 = libm::cosf(w0);
        let sin_w0 = libm::sinf(w0);
        let alpha = sin_w0 / (2.0 * quality_factor);
        // Standard RBJ notch coefficients.
        let b0 = 1.0;
        let b1 = -2.0 * cos_w0;
        let b2 = 1.0;
        let a0 = 1.0 + alpha;
        let a1 = -2.0 * cos_w0;
        let a2 = 1.0 - alpha;
        // Normalise by a0 so the difference equation has leading coefficient 1.
        Self {
            b0: b0 / a0,
            b1: b1 / a0,
            b2: b2 / a0,
            a1: a1 / a0,
            a2: a2 / a0,
            prev_x: [0.0; 2],
            prev_y: [0.0; 2],
        }
    }

    /// Reset the filter state (e.g. on a new channel).
    pub fn reset(&mut self) {
        self.prev_x = [0.0; 2];
        self.prev_y = [0.0; 2];
    }
}

impl DspStage for Notch50Hz {
    #[inline]
    fn process(&mut self, sample: f32) -> f32 {
        let x0 = sample;
        let x1 = self.prev_x[0];
        let x2 = self.prev_x[1];
        let y1 = self.prev_y[0];
        let y2 = self.prev_y[1];
        let y0 = self.b0 * x0 + self.b1 * x1 + self.b2 * x2 - self.a1 * y1 - self.a2 * y2;
        self.prev_x = [x0, x1];
        self.prev_y = [y0, y1];
        y0
    }
}

/// A scalar statistic accumulator used to sanity-check the host test path.
#[derive(Debug, Clone, Default)]
pub struct RunningMean {
    count: u64,
    mean: f32,
}

impl RunningMean {
    /// Construct a new empty accumulator.
    #[must_use]
    pub const fn new() -> Self {
        Self {
            count: 0,
            mean: 0.0,
        }
    }

    /// Incorporate a new sample into the running mean.
    pub fn update(&mut self, sample: f32) {
        self.count = self.count.saturating_add(1);
        // Welford-style update to keep the code numerically tidy for tests.
        let delta = sample - self.mean;
        // count is bounded by the simulator's run length; the cast is exact for
        // any realistic sample count and we accept the theoretical precision
        // loss above 2^24 samples.
        #[allow(clippy::cast_precision_loss)]
        let n = self.count as f32;
        self.mean += delta / n;
    }

    /// Return the current mean.
    #[must_use]
    pub fn value(&self) -> f32 {
        self.mean
    }

    /// Number of samples seen so far.
    #[must_use]
    pub fn count(&self) -> u64 {
        self.count
    }
}

#[cfg(all(test, feature = "std"))]
mod tests {
    use super::*;

    #[test]
    fn identity_passes_samples_through() {
        let mut s = Identity;
        assert!((s.process(0.123) - 0.123).abs() < f32::EPSILON);
        assert!((s.process(-1.0) - -1.0).abs() < f32::EPSILON);
    }

    #[test]
    fn running_mean_converges_to_known_mean() {
        let mut m = RunningMean::new();
        for x in [1.0_f32, 2.0, 3.0, 4.0, 5.0] {
            m.update(x);
        }
        assert!((m.value() - 3.0).abs() < 1e-6);
        assert_eq!(m.count(), 5);
    }

    // --- High-pass IIR ------------------------------------------------------

    #[test]
    fn high_pass_removes_dc_offset() {
        // A constant signal should decay to zero through the high-pass.
        let mut hp = HighPassIir::new(1.0, 1000.0);
        let mut last = 1.0_f32;
        for _ in 0..10_000 {
            last = hp.process(1.0);
        }
        assert!(last.abs() < 1e-3, "DC not removed: {last}");
    }

    #[test]
    fn high_pass_preserves_high_frequency() {
        // A signal well above the cutoff should pass largely unchanged.
        let fs = 1000.0_f32;
        let fc = 1.0;
        let mut hp = HighPassIir::new(fc, fs);
        // 100 Hz sine, well above the 1 Hz cutoff.
        let freq = 100.0_f32;
        let mut max_out = 0.0_f32;
        // Warm up so the transient settles.
        for n in 0..1000 {
            let _ = hp.process((2.0 * core::f32::consts::PI * freq * n as f32 / fs).sin());
        }
        for n in 1000..2000 {
            let out = hp.process((2.0 * core::f32::consts::PI * freq * n as f32 / fs).sin());
            max_out = max_out.max(out.abs());
        }
        // Should pass most of the amplitude (high-pass at 1 Hz, signal at 100 Hz).
        assert!(max_out > 0.9, "high-frequency signal attenuated: {max_out}");
    }

    #[test]
    fn high_pass_removes_slow_drift_but_keeps_spike() {
        // A slow drift (0.01 Hz) plus a fast spike-like pulse should keep the
        // spike and drop the drift.
        let mut hp = HighPassIir::new(1.0, 1000.0);
        let mut out_max = 0.0_f32;
        let mut out_min = 0.0_f32;
        for n in 0..10_000 {
            let drift = (2.0 * core::f32::consts::PI * 0.01 * n as f32 / 1000.0).sin() * 5.0;
            // A brief spike-like pulse at n=5000.
            let spike = if (4995..=5005).contains(&n) { 3.0 } else { 0.0 };
            let out = hp.process(drift + spike);
            out_max = out_max.max(out);
            out_min = out_min.min(out);
        }
        // The spike (amplitude 3) should survive; the drift (amplitude 5) should
        // not. So the output range should be dominated by the spike, not the
        // drift. Tolerate some residual drift.
        assert!(out_max > 2.5, "spike peak lost: {out_max}");
        assert!(out_min > -3.0, "drift not removed: {out_min}");
    }

    // --- 50 Hz notch --------------------------------------------------------

    #[test]
    fn notch_attenuates_50hz() {
        let fs = 1000.0_f32;
        let mut notch = Notch50Hz::new(fs, 35.0);
        // 50 Hz sine at amplitude 1.
        let freq = 50.0_f32;
        // Warm up.
        for n in 0..2000 {
            let _ = notch.process((2.0 * core::f32::consts::PI * freq * n as f32 / fs).sin());
        }
        let mut max_out = 0.0_f32;
        for n in 2000..4000 {
            let out = notch.process((2.0 * core::f32::consts::PI * freq * n as f32 / fs).sin());
            max_out = max_out.max(out.abs());
        }
        // 50 Hz should be heavily attenuated.
        assert!(max_out < 0.1, "50 Hz not attenuated: {max_out}");
    }

    #[test]
    fn notch_preserves_off_band_signal() {
        let fs = 1000.0_f32;
        let mut notch = Notch50Hz::new(fs, 35.0);
        // 100 Hz sine — well away from the 50 Hz notch.
        let freq = 100.0_f32;
        for n in 0..2000 {
            let _ = notch.process((2.0 * core::f32::consts::PI * freq * n as f32 / fs).sin());
        }
        let mut max_out = 0.0_f32;
        for n in 2000..4000 {
            let out = notch.process((2.0 * core::f32::consts::PI * freq * n as f32 / fs).sin());
            max_out = max_out.max(out.abs());
        }
        assert!(max_out > 0.9, "off-band signal attenuated: {max_out}");
    }

    #[test]
    fn notch_reset_clears_state() {
        let mut notch = Notch50Hz::new(1000.0, 35.0);
        // Cram some signal through.
        for i in 0..100 {
            let _ = notch.process(i as f32 * 0.1);
        }
        notch.reset();
        // After reset, processing a zero input should give zero output.
        let out = notch.process(0.0);
        assert!(out.abs() < 1e-6, "reset did not clear state: {out}");
    }
}
