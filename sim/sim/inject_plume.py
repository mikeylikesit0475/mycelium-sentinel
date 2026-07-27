#!/usr/bin/env python3
"""Inject a contaminant plume and watch the detector respond.

Usage:
    uv run python -m sim.inject_plume --contaminant cadmium --origin 3,1
    uv run python -m sim.inject_plume --origin 1,1 --mass 2000

Dumps a live, scrolling view of the plume spreading across the 32x32 grid,
the electrode readings, and the detection/arrival times. The sim-clock
factor is shown at all times (ADR-006).
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from sim.clock import SimClock
from sim.lead_time import lead_time_summary, measure_lead_time, measure_lead_time_distribution
from sim.transport import AdvectionDiffusionGrid, TransportConfig

CONTAMINANTS = {
    "cadmium": {"label": "Cd²⁺", "k_rate": 5.0, "k_amp": 0.5},
    "lead": {"label": "Pb²⁺", "k_rate": 4.0, "k_amp": 0.4},
    "mercury": {"label": "Hg²⁺", "k_rate": 6.0, "k_amp": 0.6},
}


def render_grid(grid: AdvectionDiffusionGrid, electrodes: np.ndarray) -> str:
    """Render a compact ASCII view of the grid + electrode readings."""
    c = grid.concentration
    n = grid.config.grid_size
    # Downsample to 16x16 for the terminal.
    step = n // 16
    chars = " .:-=+*#%@"
    lines = []
    for r in range(0, n, step):
        row = ""
        for col in range(0, n, step):
            val = c[r, col]
            idx = min(int(val / 50.0 * (len(chars) - 1)), len(chars) - 1)
            row += chars[max(idx, 0)]
        lines.append(row)
    lines.append("")
    lines.append(f"  total mass: {grid.total_mass:.1f}  |  t={grid.time:.1f}s")
    lines.append("  electrode readings (4x4 subgrid):")
    for i in range(4):
        vals = "  ".join(f"{electrodes[i, j]:6.2f}" for j in range(4))
        lines.append(f"    {vals}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject a contaminant plume.")
    parser.add_argument("--contaminant", default="cadmium", choices=CONTAMINANTS.keys())
    parser.add_argument("--origin", default="3,1", help="grid cell 'row,col'")
    parser.add_argument("--mass", type=float, default=1000.0)
    parser.add_argument("--steps", type=int, default=200, help="transport steps to animate")
    parser.add_argument("--factor", type=float, default=60.0, help="sim-clock factor")
    parser.add_argument(
        "--no-animation", action="store_true", help="skip the animation, just show results"
    )
    args = parser.parse_args()

    origin = tuple(int(x) for x in args.origin.split(","))
    cont = CONTAMINANTS[args.contaminant]
    clock = SimClock(factor=args.factor)

    print(f"[mycelium-sentinel] sim-clock: {clock.factor_label()}")
    print(f"[mycelium-sentinel] injecting {cont['label']} ({args.contaminant})")
    print(f"                    origin: {origin}  mass: {args.mass}")
    print(
        f"                    coupling: k_rate={cont['k_rate']} k_amp={cont['k_amp']} (ILLUSTRATIVE — ADR-008)"
    )
    print()

    transport = TransportConfig(diffusion=0.05, advection=(0.01, 0.005), dt=0.5)
    grid = AdvectionDiffusionGrid(transport)
    grid.inject(origin[0], origin[1], mass=args.mass)

    if not args.no_animation:
        for step in range(args.steps):
            grid.step()
            electrodes = grid.electrode_readings()
            print("\033[2J\033[H")  # clear screen + home
            print(
                f"=== Mycelial Sentinel — {cont['label']} plume (sim-clock {clock.factor_label()}) ==="
            )
            print(f"    step {step + 1}/{args.steps}  virtual t={grid.time:.1f}s")
            print()
            print(render_grid(grid, electrodes))
            time.sleep(0.05)

    # Measure the lead time.
    print()
    print("=== Lead-time measurement ===")
    result = measure_lead_time(origin, transport=transport)
    if result.lead_time == float("-inf"):
        print("  detection or arrival did not fire within the time window")
        return 1
    print(f"  origin:           {result.origin}")
    print(f"  detection time:   {result.detection_time:.1f}s (virtual)")
    print(f"  arrival time:     {result.arrival_time:.1f}s (virtual)")
    print(f"  lead time:        {result.lead_time:.1f}s (arrival - detection)")
    print(
        f"  {'DETECTED BEFORE ARRIVAL ✓' if result.lead_time > 0 else 'ARRIVED BEFORE DETECTION ✗'}"
    )
    print()

    # Distribution across origins.
    print("=== Lead-time distribution (multiple origins) ===")
    results = measure_lead_time_distribution(
        origins=[(3, 1), (1, 3), (3, 3), (2, 1), (1, 2)],
        transport=transport,
    )
    summary = lead_time_summary(results)
    for r in results:
        print(
            f"  origin {r.origin}: lead={r.lead_time:.1f}s  detect={r.detection_time:.1f}s  arrive={r.arrival_time:.1f}s"
        )
    print()
    print(f"  median: {summary['median']:.1f}s   mean: {summary['mean']:.1f}s")
    print(f"  all positive (detection before arrival): {summary['all_positive']}")
    print()
    print(f"  sim-clock: {clock.factor_label()} — never mistake for real time (ADR-006)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
