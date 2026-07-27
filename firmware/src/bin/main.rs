//! Mycelium Sentinel firmware binary entry point.
//!
//! Boots on an STM32F407 (Discovery board) under Renode.
//!
//! Sprint 0.2: boot banner on UART4.
//! Sprint 0.4: virtual UART bridge — echo frames back as ACKs.
//! Sprint 1.5: full signal chain — sample frames in, event frames out.
//!   incoming sample frames (channel 0-15, payload = f32 sample) are run
//!   through that channel's high-pass + notch + spike-detector + feature
//!   extractor; when a spike fires, a packed `SpikeFeatures` event frame goes
//!   out on TX. Channel 0xFF is reserved for the echo/bridge test.
//!
//! Built only for `thumbv7em-none-eabi` via `.cargo/config.toml` + `bin-build`.

#![no_std]
#![no_main]
#![allow(clippy::missing_docs_in_private_items)]
// Mutable static references are the standard no_std pattern for static
// pipeline state. We're on edition 2021; the 2024-compat lint is forward-looking.
#![allow(static_mut_refs)]

use core::panic::PanicInfo;
use core::ptr::{read_volatile, write_volatile};

use firmware::dsp::{DspStage, HighPassIir, Notch50Hz};
use firmware::features::{pack_features, FeatureExtractor, SpikeFeatures};
use firmware::protocol::{Frame, FrameDecoder, EOF, SOF};
use firmware::spike_detect::SpikeDetector;
use firmware::FW_VERSION;

const NUM_CHANNELS: usize = 16;
const ECHO_CHANNEL: u8 = 0xFF;
const SAMPLE_RATE: f32 = 1000.0;
const HP_CUTOFF: f32 = 1.0;
const NOTCH_Q: f32 = 35.0;

/// UART4 base address (STM32F407, per Renode `stm32f4.repl`).
const UART4_BASE: usize = 0x4000_4C00;
const RCC_BASE: usize = 0x4002_3800;
const RCC_APB1ENR_OFFSET: usize = 0x40;
const RCC_APB1ENR_UART4: u32 = 1 << 19;

const USART_SR: usize = 0x00;
const USART_DR: usize = 0x04;
const USART_BRR: usize = 0x08;
const USART_CR1: usize = 0x0C;
const USART_CR2: usize = 0x10;

const SR_TXE: u32 = 1 << 7;
const SR_RXNE: u32 = 1 << 5;
const CR1_UE: u32 = 1 << 13;
const CR1_TE: u32 = 1 << 3;
const CR1_RE: u32 = 1 << 2;

// GPIO D (the UserLED pin, per stm32f4_discovery.repl). Pin 12 is wired to
// the LED; we drive it high when a spike is detected so the simulator can
// read it via Renode and actuate the neutralisation valve (Sprint 2.4).
const GPIOD_BASE: usize = 0x4002_0C00;
const GPIO_MODER: usize = 0x00;
const GPIO_ODR: usize = 0x14;
const RCC_AHB1ENR_OFFSET: usize = 0x30;
const RCC_AHB1ENR_GPIOD: u32 = 1 << 3;
const VALVE_PIN: u32 = 12;

/// One channel's signal chain: high-pass → notch → spike detector → features.
struct ChannelPipeline {
    hp: HighPassIir,
    notch: Notch50Hz,
    detector: SpikeDetector,
    features: FeatureExtractor,
    sample_index: u64,
}

impl ChannelPipeline {
    fn new() -> Self {
        Self {
            hp: HighPassIir::new(HP_CUTOFF, SAMPLE_RATE),
            notch: Notch50Hz::new(SAMPLE_RATE, NOTCH_Q),
            detector: SpikeDetector::default_detector(),
            features: FeatureExtractor::new(),
            sample_index: 0,
        }
    }

    fn process(&mut self, raw: f32) -> Option<SpikeFeatures> {
        let hp = self.hp.process(raw);
        let filtered = self.notch.process(hp);
        let idx = self.sample_index;
        self.sample_index = self.sample_index.wrapping_add(1);
        if let Some(amp) = self.detector.process(filtered) {
            return Some(self.features.record(amp, idx, SAMPLE_RATE));
        }
        None
    }
}

/// The 16-channel pipeline state. Static because there's no heap. Initialised
/// in `main` by writing constructed `ChannelPipeline`s into the array slots.
/// The inline const `const { MaybeUninit::uninit() }` avoids the `Copy` bound
/// that a plain `[MaybeUninit::UNINIT; N]` array literal would impose.
static mut PIPELINES: [MaybeUninit<ChannelPipeline>; NUM_CHANNELS] =
    [const { MaybeUninit::uninit() }; NUM_CHANNELS];

use core::mem::MaybeUninit;

fn init_pipelines() {
    // Safety: single-threaded boot, no concurrent access. Each slot is written
    // once before any read.
    unsafe {
        for slot in &mut PIPELINES {
            slot.write(ChannelPipeline::new());
        }
    }
}

fn pipeline_mut(channel: u8) -> &'static mut ChannelPipeline {
    let idx = usize::from(channel).min(NUM_CHANNELS - 1);
    // Safety: single-threaded RX path, no data race. The slot was initialised
    // in `init_pipelines` at boot.
    unsafe { PIPELINES[idx].assume_init_mut() }
}

fn uart4_init() {
    let apb1enr = (RCC_BASE + RCC_APB1ENR_OFFSET) as *mut u32;
    let mut v = unsafe { read_volatile(apb1enr) };
    v |= RCC_APB1ENR_UART4;
    unsafe {
        write_volatile(apb1enr, v);
    }
    let cr1 = (UART4_BASE + USART_CR1) as *mut u32;
    let cr2 = (UART4_BASE + USART_CR2) as *mut u32;
    let brr = (UART4_BASE + USART_BRR) as *mut u32;
    unsafe {
        write_volatile(cr1, 0);
        write_volatile(cr2, 0);
        write_volatile(brr, 364);
        write_volatile(cr1, CR1_UE | CR1_TE | CR1_RE);
    }
}

/// Initialise GPIO D pin 12 as a push-pull output (the valve actuation line).
fn valve_gpio_init() {
    // Enable the GPIOD clock on AHB1.
    let ahb1enr = (RCC_BASE + RCC_AHB1ENR_OFFSET) as *mut u32;
    let mut v = unsafe { read_volatile(ahb1enr) };
    v |= RCC_AHB1ENR_GPIOD;
    unsafe {
        write_volatile(ahb1enr, v);
    }
    // Set pin 12 to output mode (MODER bits 2*pin : 2*pin+1 = 01).
    let moder = (GPIOD_BASE + GPIO_MODER) as *mut u32;
    let mut m = unsafe { read_volatile(moder) };
    m &= !(0b11 << (2 * VALVE_PIN));
    m |= 0b01 << (2 * VALVE_PIN);
    unsafe {
        write_volatile(moder, m);
    }
    // Start with the valve off (pin low).
    valve_set(false);
}

/// Drive the valve actuation line high (true) or low (false).
fn valve_set(on: bool) {
    let odr = (GPIOD_BASE + GPIO_ODR) as *mut u32;
    let mut v = unsafe { read_volatile(odr) };
    if on {
        v |= 1 << VALVE_PIN;
    } else {
        v &= !(1 << VALVE_PIN);
    }
    unsafe {
        write_volatile(odr, v);
    }
}

fn uart_putc(byte: u8) {
    let sr = (UART4_BASE + USART_SR) as *mut u32;
    let dr = (UART4_BASE + USART_DR) as *mut u32;
    while unsafe { read_volatile(sr) } & SR_TXE == 0 {}
    unsafe {
        write_volatile(dr, u32::from(byte));
    }
}

fn uart_write(bytes: &[u8]) {
    for &b in bytes {
        uart_putc(b);
    }
}

fn uart_getc() -> Option<u8> {
    let sr = (UART4_BASE + USART_SR) as *mut u32;
    let dr = (UART4_BASE + USART_DR) as *mut u32;
    if unsafe { read_volatile(sr) } & SR_RXNE == 0 {
        return None;
    }
    let word = unsafe { read_volatile(dr) };
    #[allow(clippy::cast_possible_truncation)]
    Some(word as u8)
}

fn uart_write_frame(frame: &Frame) {
    let mut buf = [0u8; firmware::protocol::MAX_PAYLOAD + 4];
    if let Some(n) = frame.encode_into(&mut buf) {
        uart_write(&buf[..n]);
    }
}

fn boot_banner() {
    uart_write(b"\r\n[mycelium-sentinel] firmware ");
    uart_write(FW_VERSION.as_bytes());
    uart_write(b" booted on STM32F407 (Renode)\r\n");
}

/// Echo an incoming frame back as an ACK frame (channel 0xFF bridge test).
fn echo_frame(incoming: &Frame) {
    let mut payload = [0u8; firmware::protocol::MAX_PAYLOAD];
    payload[0] = 0xAC;
    let n = usize::from(incoming.len).min(firmware::protocol::MAX_PAYLOAD - 1);
    payload[1..=n].copy_from_slice(&incoming.payload[..n]);
    let ack = Frame::from_slice(incoming.channel, &payload[..=n]);
    if let Some(f) = ack {
        uart_write_frame(&f);
    }
}

/// Decode a 4-byte little-endian f32 from a payload slice.
fn decode_f32(payload: &[u8]) -> Option<f32> {
    if payload.len() < 4 {
        return None;
    }
    let bytes = [payload[0], payload[1], payload[2], payload[3]];
    Some(f32::from_le_bytes(bytes))
}

/// Handle a sample frame: run the channel pipeline, emit an event frame if a
/// spike fired.
fn handle_sample_frame(channel: u8, payload: &[u8]) {
    let Some(sample) = decode_f32(payload) else {
        return;
    };
    // Safety: PIPELINES is a static array of 16 entries; we access one element
    // mutably. The main loop is single-threaded (no interrupts on the RX path
    // yet) so there's no data race.
    let pipeline = pipeline_mut(channel);
    if let Some(features) = pipeline.process(sample) {
        emit_event_frame(channel, &features);
    }
}

/// Pack features into a frame and send it on UART4 TX. Also drives the valve
/// GPIO high so the simulator can read it via Renode and actuate the
/// neutralisation (Sprint 2.4).
fn emit_event_frame(channel: u8, features: &SpikeFeatures) {
    let mut payload = [0u8; firmware::protocol::MAX_PAYLOAD];
    let n = pack_features(features, &mut payload).unwrap_or(0);
    if n > 0 {
        let frame = Frame::from_slice(channel, &payload[..n]);
        if let Some(f) = frame {
            uart_write_frame(&f);
        }
    }
    // Drive the valve line high: a spike was detected, actuate neutralisation.
    valve_set(true);
}

/// Dispatch an incoming frame: channel 0xFF = echo test, 0-15 = sample frame.
fn handle_frame(frame: &Frame) {
    if frame.channel == ECHO_CHANNEL {
        echo_frame(frame);
        return;
    }
    if frame.channel < u8::try_from(NUM_CHANNELS).unwrap_or(u8::MAX) {
        handle_sample_frame(frame.channel, frame.payload_bytes());
    }
}

#[cortex_m_rt::entry]
fn main() -> ! {
    init_pipelines();
    uart4_init();
    valve_gpio_init();
    boot_banner();

    let mut decoder = FrameDecoder::new();
    loop {
        if let Some(byte) = uart_getc() {
            if let Some(frame) = decoder.feed(byte) {
                handle_frame(&frame);
            }
            continue;
        }
        for _ in 0..100 {
            cortex_m::asm::nop();
        }
    }
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    uart_write(b"\r\n[mycelium-sentinel] PANIC\r\n");
    loop {
        cortex_m::asm::bkpt();
    }
}

const _SOF: u8 = SOF;
const _EOF: u8 = EOF;
