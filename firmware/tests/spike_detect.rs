//! Host-side tests for the spike-detection pipeline.

use firmware::spike_detect::{SpikeDetector, DEFAULT_K, DEFAULT_WINDOW};

#[test]
fn detector_does_not_fire_on_pure_noise() {
    let mut det = SpikeDetector::default_detector();
    let mut state: u32 = 2024;
    let mut fires = 0;
    for _ in 0..(DEFAULT_WINDOW * 4) {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        let n = ((state >> 8) as f32 / (1u32 << 24) as f32 - 0.5) * 0.04;
        if det.process(n).is_some() {
            fires += 1;
        }
    }
    // Tolerate a tiny number of false positives but not many.
    assert!(fires < 5, "too many false positives on pure noise: {fires}");
}

#[test]
fn detector_fires_on_repeated_spikes() {
    let mut det = SpikeDetector::default_detector();
    let mut state: u32 = 99;
    let mut fires = 0;
    // Run for many windows with a spike every 200 samples.
    for i in 0..(DEFAULT_WINDOW * 10) {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        let n = ((state >> 8) as f32 / (1u32 << 24) as f32 - 0.5) * 0.04;
        let s = if i > DEFAULT_WINDOW && i % 200 == 0 {
            2.0
        } else {
            n
        };
        if det.process(s).is_some() {
            fires += 1;
        }
    }
    assert!(fires >= 5, "missed spikes: only {fires} fired");
}

#[test]
fn default_k_is_five_sigma() {
    assert!((DEFAULT_K - 5.0).abs() < 1e-6);
}
