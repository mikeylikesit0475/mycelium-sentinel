"""Lead-time regression floor (Sprint 2.5).

This test asserts that the detection lead time doesn't degrade below a recorded
floor. If a change to the transport, coupling, or detector parameters makes
the lead time worse, this test fails the build — that's the regression floor in
CI (BACKLOG.md Sprint 2.5).

The floor is set conservatively based on the current measured performance.
When the metric improves, the floor can be raised; it should never be lowered
without a documented reason.
"""

from __future__ import annotations

import pytest

from sim.coupling import CouplingConfig
from sim.hawkes import HawkesConfig
from sim.lead_time import lead_time_summary, measure_lead_time_distribution
from sim.transport import TransportConfig

# The recorded floor for the median lead time across the default origin
# distribution (virtual seconds). Set conservatively — the current measured
# median is well above this. Raises are welcome; lowers need a reason.
LEAD_TIME_FLOOR_SECONDS = 50.0


@pytest.mark.slow
def test_lead_time_above_regression_floor() -> None:
    """The median lead time across plume origins must stay above the floor."""
    # Use the faster transport config so the test runs in CI in reasonable time.
    transport = TransportConfig(diffusion=0.05, advection=(0.01, 0.005), dt=0.5)
    results = measure_lead_time_distribution(
        origins=[(3, 1), (1, 3), (3, 3), (2, 1), (1, 2)],
        transport=transport,
        base_hawkes=HawkesConfig(),
        coupling=CouplingConfig(),
    )
    summary = lead_time_summary(results)
    assert summary["n"] == 5, f"expected 5 results, got {summary['n']}"
    assert summary["median"] > LEAD_TIME_FLOOR_SECONDS, (
        f"median lead time {summary['median']:.1f}s fell below the "
        f"regression floor of {LEAD_TIME_FLOOR_SECONDS}s — a change degraded "
        "the detection lead time. Either fix the regression or document why "
        "the floor should be lowered."
    )
    assert summary["all_positive"], (
        "at least one origin has a non-positive lead time — detection fired "
        "after the plume arrived, which breaks the product's value proposition"
    )


def test_lead_time_floor_is_documented_and_positive() -> None:
    """The floor itself must be a sane positive number."""
    assert LEAD_TIME_FLOOR_SECONDS > 0.0
