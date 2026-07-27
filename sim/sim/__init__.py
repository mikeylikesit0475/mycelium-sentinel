"""Mycelium Sentinel simulator.

The simulator generates the biology — a 2D advection-diffusion plume, Hawkes
spike trains on a 4x4 electrode grid, and a realistic electrode/ADC front end.
It feeds real firmware over a virtual UART (ARCHITECTURE.md §3).

Sprint 0.1 only ships the package skeleton. The advection-diffusion grid lands
in Sprint 0.5, the Hawkes model in Sprint 0.6.
"""

__all__: list[str] = []
