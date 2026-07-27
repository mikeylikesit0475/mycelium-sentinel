#![cfg_attr(not(feature = "std"), no_std)]
//! Firmware for the Mycelium Sentinel edge node.
//!
//! Architecture note: this crate compiles two ways —
//! - as `no_std` for `thumbv7em-none-eabi` (the binary that boots in Renode), and
//! - with the `std` feature for host unit tests of the DSP chain
//!   (ARCHITECTURE.md §7, row 1).
//!
//! Sprint 0.1 only needs this to compile and for host tests to pass. Real filtering,
//! spike detection and feature extraction land in Sprint 1.

// Lints are configured at the workspace level (Cargo.toml [workspace.lints]).
// We keep the crate doc-light during Sprint 0.1; full module docs land with the
// implementations in Sprint 1.

pub mod dsp;
pub mod protocol;

/// Firmware version reported over the UART at boot.
pub const FW_VERSION: &str = "0.0.0";

#[cfg(feature = "std")]
extern crate std;

/// Convenience re-export for binary builds.
#[cfg(feature = "bin-build")]
pub use dsp::DspStage;
