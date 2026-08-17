"""Acceptance tests for the chrono reference model (VER-CTL-001,
VER-CNT-002, VER-DSP-003 exercised against the model itself)."""

import random

from chrono import Chrono


def test_toggle_preserves_count():  # CTL-SS-001
    c = Chrono()
    c.press_startstop()
    c.tick()
    c.tick()
    c.press_startstop()
    c.tick()  # stopped: must hold
    assert (c.count, c.running) == (2, False)
    c.press_startstop()
    c.tick()
    assert (c.count, c.running) == (3, True)


def test_reset_clears_and_stops():  # CTL-RST-001
    c = Chrono()
    c.press_startstop()
    for _ in range(7):
        c.tick()
    c.press_reset()
    assert (c.count, c.running) == (0, False)


def test_wrap_at_99():  # VER-CNT-002
    c = Chrono()
    c.press_startstop()
    for _ in range(99):
        c.tick()
    assert c.count == 99 and c.bcd == (9, 9)
    c.tick()
    assert c.count == 0 and c.running is True


def test_bcd_invariant_random():  # VER-DSP-003 over VER-CTL-001-style sequences
    rng = random.Random(1)
    c = Chrono()
    for _ in range(10_000):
        rng.choice([c.press_reset, c.press_startstop, c.tick])()
        hi, lo = c.bcd
        assert 0 <= hi <= 9 and 0 <= lo <= 9
