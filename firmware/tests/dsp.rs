//! Host-side unit tests for the firmware DSP blocks.
//!
//! These run under `cargo test --features std`. They exercise the same code paths
//! that run on the emulated MCU (CLAUDE.md: "Don't let a block become
//! emulator-only.").

use firmware::dsp::{DspStage, Identity, RunningMean};

#[test]
fn identity_stage_is_transparent() {
    let mut s = Identity;
    for x in [-2.0_f32, -0.5, 0.0, 0.5, 2.0] {
        assert!((s.process(x) - x).abs() < f32::EPSILON);
    }
}

#[test]
fn running_mean_is_stable_under_constant_input() {
    let mut m = RunningMean::new();
    for _ in 0..1000 {
        m.update(7.5);
    }
    assert!((m.value() - 7.5).abs() < 1e-5);
}

#[test]
fn running_mean_handles_single_sample() {
    let mut m = RunningMean::new();
    m.update(42.0);
    assert!((m.value() - 42.0).abs() < 1e-6);
}
