//! Digital signal processing blocks for the Mycelium Sentinel firmware.
//!
//! Host-testable and on-target: the same code paths run under `cargo test` with
//! the `std` feature and inside the emulated MCU. (CLAUDE.md: "Don't let a block
//! become emulator-only.")
//!
//! Sprint 0.1 ships a placeholder identity stage so the workspace compiles and the
//! test matrix is wired up. The real high-pass IIR, 50 Hz notch, MAD-based spike
//! detector and feature extractor are implemented in Sprints 1.2–1.4.

/// A processing stage that takes one sample in and produces one sample out.
pub trait DspStage {
    /// Process a single sample, mutating internal state as needed.
    fn process(&mut self, sample: f32) -> f32;
}

/// Pass-through stage used to wire up the test harness before real filters land.
pub struct Identity;

impl DspStage for Identity {
    #[inline]
    fn process(&mut self, sample: f32) -> f32 {
        sample
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
}
