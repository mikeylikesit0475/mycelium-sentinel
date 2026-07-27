use std::env;
use std::fs::copy;
use std::path::PathBuf;

fn main() {
    // Only relevant for the embedded binary build. Skip for host tests.
    let target = env::var("TARGET").unwrap_or_default();
    if !target.starts_with("thumbv7em-none-eabi") && !target.contains("none-eabi") {
        return;
    }

    // cortex-m-rt's build script INCLUDEs `memory.x` from its OUT_DIR. We place
    // it there so the generated link.x picks up our STM32F407 memory map. But
    // cortex-m-rt runs in its own OUT_DIR, so we also need to make our memory.x
    // discoverable via the linker search path — copy it to OUR out dir and add
    // that to the link search path. The standard pattern is to add a link-search
    // to the firmware crate's OUT_DIR so link.x can find our memory.x.
    let out = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR set"));
    let src = PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR set"))
        .join("memory.x");
    let dst = out.join("memory.x");
    if let Err(e) = copy(&src, &dst) {
        panic!("failed to copy memory.x to {}: {e}", dst.display());
    }

    println!("cargo:rerun-if-changed=memory.x");

    // Make our OUT_DIR visible to the linker so link.x's `INCLUDE memory.x`
    // resolves. cortex-m-rt only adds its own OUT_DIR to the search path; we
    // add ours too.
    println!("cargo:rustc-link-search={}", out.display());

    // Use the linker script shipped by cortex-m-rt (generated into its OUT_DIR).
    // `-Tlink.x` + `--nmagic` is the canonical cortex-m-rt link configuration.
    println!("cargo:rustc-link-arg=-Tlink.x");
    println!("cargo:rustc-link-arg=--nmagic");
}
