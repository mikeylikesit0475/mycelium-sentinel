/* STM32F407 memory map.
 *
 * Used by cortex-m-rt's generated link.x (it INCLUDEs this file). The values
 * match the Renode `stm32f4.repl` platform description:
 *   - flash at 0x08000000, 1 MiB (the F407VG die; the .repl declares 2 MiB which
 *     would also be fine — 1 MiB is the conservative documented F407 size)
 *   - main SRAM at 0x20000000, 192 KiB (the documented F407 size)
 *
 * CCM RAM (0x10000000, 64 KiB) is intentionally not in the default link regions:
 * it's not accessible by DMA and complicates the boot. We can opt-in later if a
 * stage needs the scratch space.
 */

MEMORY
{
    FLASH : ORIGIN = 0x08000000, LENGTH = 1024K
    RAM   : ORIGIN = 0x20000000, LENGTH = 192K
}

/* The stack starts at the top of main RAM. */
_stack_top = ORIGIN(RAM) + LENGTH(RAM);