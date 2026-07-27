"""Smoke test for the sim package.

Real simulator tests land in Sprint 0.5 (diffusion mass conservation) and
Sprint 0.6 (Hawkes ISI distribution). This test only asserts the package imports.
"""

import sim


def test_sim_imports() -> None:
    assert hasattr(sim, "__all__")
