//! Mycelium Sentinel firmware binary entry point.
//!
//! Sprint 0.2: a real `no_std` binary that boots on an STM32F407 (Discovery board)
//! under Renode and writes a boot banner to UART4 so the emulator's UART analyzer
//! has something to show. Real DSP wiring lands in Sprint 1.
//!
//! Built only for `thumbv7em-none-eabi` via `.cargo/config.toml` + `bin-build`.

#![no_std]
#![no_main]
#![allow(clippy::missing_docs_in_private_items)]

use core::panic::PanicInfo;
use core::ptr::{read_volatile, write_volatile};

use firmware::FW_VERSION;

/// UART4 base address (STM32F407, per Renode `stm32f4.repl`).
const UART4_BASE: usize = 0x4000_4C00;
/// RCC base, APB1 enable register offset. UART4 is on APB1, bit 19 (RM0090 §7.4).
const RCC_BASE: usize = 0x4002_3800;
const RCC_APB1ENR_OFFSET: usize = 0x40;
const RCC_APB1ENR_UART4: u32 = 1 << 19;

// STM32F4 USART register offsets (RM0090 §26.6).
const USART_SR: usize = 0x00;
const USART_DR: usize = 0x04;
const USART_BRR: usize = 0x08;
const USART_CR1: usize = 0x0C;
const USART_CR2: usize = 0x10;

/// SR bit 7: transmit data register empty (TXE).
const SR_TXE: u32 = 1 << 7;
/// CR1 bit 13: USART enable (UE).
const CR1_UE: u32 = 1 << 13;
/// CR1 bit 3: transmitter enable (TE).
const CR1_TE: u32 = 1 << 3;

/// Initialise UART4: enable its clock, set the baud rate, enable TX.
///
/// Renode's `STM32_UART` peripheral checks the UE/TE bits before accepting
/// writes; without this it logs "transmitter is not enabled, dropping".
fn uart4_init() {
    // Enable the UART4 clock on APB1.
    let apb1enr = (RCC_BASE + RCC_APB1ENR_OFFSET) as *mut u32;
    let mut v = unsafe { read_volatile(apb1enr) };
    v |= RCC_APB1ENR_UART4;
    unsafe {
        write_volatile(apb1enr, v);
    }

    // Configure UART4: 115200 baud, 8N1, transmitter enabled, USART enabled.
    // BRR for 115200 from APB1 (42 MHz) ~= 0x16D (rounding 42e6/115200 ≈ 364).
    let cr1 = (UART4_BASE + USART_CR1) as *mut u32;
    let cr2 = (UART4_BASE + USART_CR2) as *mut u32;
    let brr = (UART4_BASE + USART_BRR) as *mut u32;

    // Disable UE while we configure.
    unsafe {
        write_volatile(cr1, 0);
        // CR2 reset value is 0; stop bits = 1 (default). Write 0 to be explicit.
        write_volatile(cr2, 0);
        // Baud rate: APB1 is 42 MHz on the F407, /115200 ≈ 364.5 -> 0x16C or 0x16D.
        write_volatile(brr, 364);
        // Enable UE + TE.
        write_volatile(cr1, CR1_UE | CR1_TE);
    }
}

/// Write one byte to UART4, polling TXE.
fn uart_putc(byte: u8) {
    let sr = (UART4_BASE + USART_SR) as *mut u32;
    let dr = (UART4_BASE + USART_DR) as *mut u32;
    // Spin until the transmit data register is empty. The read is a volatile
    // MMIO load; the address is fixed and owned by the UART peripheral.
    while unsafe { read_volatile(sr) } & SR_TXE == 0 {}
    // Safety: writing to the UART data register is a normal MMIO store; the
    // address is fixed and the device owns it. This is the minimum `unsafe`
    // the binary needs and why `unsafe_code = "deny"` is not workspace-wide.
    unsafe {
        write_volatile(dr, u32::from(byte));
    }
}

/// Write a byte slice to UART4.
fn uart_write(bytes: &[u8]) {
    for &b in bytes {
        uart_putc(b);
    }
}

/// Boot banner: printed once on reset so the Renode console has an observable
/// signal that real firmware is running.
fn boot_banner() {
    uart_write(b"\r\n[mycelium-sentinel] firmware ");
    uart_write(FW_VERSION.as_bytes());
    uart_write(b" booted on STM32F407 (Renode)\r\n");
}

/// Cortex-M reset entry. The `cortex-m-rt` macro provides the reset vector and
/// calls this after `.data`/`.bss` initialisation.
#[cortex_m_rt::entry]
fn main() -> ! {
    uart4_init();
    boot_banner();

    // Spin so the emulator keeps the core alive. WFI lets Renode advance
    // the sim clock while we wait for UART input in later sprints.
    loop {
        cortex_m::asm::wfi();
    }
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    // Best-effort marker so a panic is visible in the UART analyzer too.
    uart_write(b"\r\n[mycelium-sentinel] PANIC\r\n");
    loop {
        cortex_m::asm::bkpt();
    }
}
