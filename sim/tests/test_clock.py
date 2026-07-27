"""Tests for the sim-clock acceleration (ADR-006)."""

from __future__ import annotations

import time

import pytest

from sim.clock import DEFAULT_FACTOR, SimClock


def test_factor_must_be_positive() -> None:
    with pytest.raises(ValueError):
        SimClock(factor=0.0)
    with pytest.raises(ValueError):
        SimClock(factor=-1.0)


def test_default_factor_is_60() -> None:
    assert DEFAULT_FACTOR == 60.0


def test_now_advances_at_factor_rate() -> None:
    clock = SimClock(factor=100.0)
    t0 = clock.now()
    time.sleep(0.05)
    t1 = clock.now()
    elapsed_virtual = t1 - t0
    # 0.05 wall seconds * factor 100 = ~5 virtual seconds.
    assert elapsed_virtual > 2.0, f"virtual time didn't advance fast enough: {elapsed_virtual}"
    assert elapsed_virtual < 10.0, f"virtual time advanced too fast: {elapsed_virtual}"


def test_factor_is_exposed() -> None:
    clock = SimClock(factor=42.0)
    assert clock.factor == 42.0


def test_factor_label_is_human_readable() -> None:
    assert "60x" in SimClock(factor=60.0).factor_label()
    assert "1min" in SimClock(factor=60.0).factor_label()
    assert "1h" in SimClock(factor=3600.0).factor_label()
    assert "1s" in SimClock(factor=1.0).factor_label()


def test_reset_zeros_virtual_time() -> None:
    clock = SimClock(factor=100.0)
    time.sleep(0.02)
    assert clock.now() > 0.0
    clock.reset()
    assert clock.now() < 1.0


def test_advance_adds_virtual_time() -> None:
    clock = SimClock(factor=1.0)
    t0 = clock.now()
    clock.advance(100.0)
    t1 = clock.now()
    assert t1 - t0 >= 100.0
