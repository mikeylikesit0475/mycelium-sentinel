"""Tests for the detection lead-time metric (Sprint 2.3)."""

from __future__ import annotations

import numpy as np

from sim.lead_time import (
    lead_time_summary,
    measure_lead_time,
    measure_lead_time_distribution,
)
from sim.transport import TransportConfig


def test_lead_time_is_positive_for_corner_origin() -> None:
    """A corner-origin plume should be detected before it reaches the centre."""
    # Use a faster transport for the test so it runs quickly.
    transport = TransportConfig(diffusion=0.05, advection=(0.01, 0.005), dt=0.5)
    result = measure_lead_time(origin=(3, 1), transport=transport)
    assert result.lead_time != float("-inf"), "detection or arrival never fired"
    assert result.lead_time > 0.0, (
        f"lead time should be positive (detection before arrival): {result.lead_time}"
    )


def test_detection_time_is_before_arrival_time() -> None:
    transport = TransportConfig(diffusion=0.05, advection=(0.01, 0.005), dt=0.5)
    result = measure_lead_time(origin=(1, 1), transport=transport)
    assert result.detection_time < result.arrival_time


def test_distribution_covers_multiple_origins() -> None:
    transport = TransportConfig(diffusion=0.05, advection=(0.01, 0.005), dt=0.5)
    results = measure_lead_time_distribution(
        origins=[(3, 1), (1, 3), (2, 2)],
        transport=transport,
    )
    assert len(results) == 3
    # All should have finite times.
    for r in results:
        assert r.detection_time < float("inf")
        assert r.arrival_time < float("inf")


def test_summary_reports_stats() -> None:
    transport = TransportConfig(diffusion=0.05, advection=(0.01, 0.005), dt=0.5)
    results = measure_lead_time_distribution(
        origins=[(3, 1), (1, 3)],
        transport=transport,
    )
    summary = lead_time_summary(results)
    assert summary["n"] == 2
    assert "mean" in summary
    assert "median" in summary
    assert "min" in summary
    assert "max" in summary
    assert summary["all_positive"] is True


def test_summary_handles_no_results() -> None:
    summary = lead_time_summary([])
    assert summary["n"] == 0
    assert np.isnan(summary["mean"])


def test_closer_origin_detected_earlier() -> None:
    """An origin next to an electrode should be detected earlier than one
    further from any electrode (all else equal)."""
    transport = TransportConfig(diffusion=0.05, advection=(0.0, 0.0), dt=0.5)
    # Electrodes sit at grid positions 2, 11, 20, 29 (linspace(2, 29, 4)).
    # (2, 2) is right on an electrode; (16, 16) is the grid centre, far from
    # any electrode in the early diffusion.
    near = measure_lead_time(origin=(2, 2), transport=transport)
    far = measure_lead_time(origin=(16, 16), transport=transport)
    assert near.detection_time < far.detection_time, (
        f"near origin detected at {near.detection_time}, "
        f"far at {far.detection_time} — should be the other way round"
    )
