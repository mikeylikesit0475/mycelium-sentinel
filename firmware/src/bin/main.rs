//! Mycelium Sentinel firmware binary entry point.
//!
//! Sprint 0.1: a real `no_std` binary that boots on an Cortex-M4 (nRF52840 /
//! STM32F4-class part) under Renode. It does nothing yet beyond resetting and
//! entering an idle loop — the job here is "a compiled Rust binary that the
//! emulator can load." Real DSP wiring lands in Sprint 1.
//!
//! Built only for `thumbv7em-none-eabi` via `.cargo/config.toml`.

#![no_std]
#![no_main]

use core::panic::PanicInfo;
use firmware::FW_VERSION;

/// Cortex-M reset entry. The `cortex-m-rt` macro provides the reset vector and
/// calls this after `.data`/`.bss` initialisation.
#[cortex_m_rt::entry]
fn main() -> ! {
    // A single volatile store so the binary has an observable effect on the
    // emulator (a scratch register write). Real UART output lands in Sprint 0.4.
    //
    // Safety: writing an arbitrary word to a known-free SRAM address is
    // well-defined on these parts and is the minimal observable Renode signal.
    let scratch: *mut u32 = 0x2000_0000 as *mut u32;
    unsafe {
        core::ptr::write_volatile(scratch, 0xDEAD_BEEF);
    }

    // Keep FW_VERSION referenced so dead-code lint stays quiet until Sprint 1
    // wires it into the boot banner.
    let _ = FW_VERSION;

    loop {
        // WFI keeps the core idle; Renode advances the sim clock while we wait.
        cortex_m::asm::wfi();
    }
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {
        cortex_m::asm::bkpt();
    }
}
