//! Host-side unit tests for the spike-detection pipeline.
//!
//! Real MAD-based thresholding lands in Sprint 1.3; Sprint 0.1 only checks that
//! the test target compiles and runs against the firmware crate with the `std`
//! feature. This is the place the on-target firmware code gets its first host
//! safety net.

use firmware::dsp::RunningMean;

#[test]
fn running_mean_resets_after_construction() {
    let m = RunningMean::new();
    assert_eq!(m.count(), 0);
    assert!(m.value().is_nan() || m.value() == 0.0);
}
