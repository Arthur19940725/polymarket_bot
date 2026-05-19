"""Tests for clock abstraction."""
import time
from datetime import datetime, timezone
from clock import RealClock, FakeClock


def test_real_clock_now_returns_current_utc():
    c = RealClock()
    before = datetime.now(timezone.utc).timestamp()
    got = c.now().timestamp()
    after = datetime.now(timezone.utc).timestamp()
    assert before <= got <= after


def test_real_clock_sleep_actually_sleeps():
    c = RealClock()
    t0 = time.time()
    c.sleep(0.05)
    assert time.time() - t0 >= 0.05


def test_fake_clock_starts_at_given_time():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    c = FakeClock(start)
    assert c.now() == start


def test_fake_clock_sleep_advances_virtual_time():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    c = FakeClock(start)
    c.sleep(60)
    assert c.now() == datetime(2026, 1, 1, 0, 1, 0, tzinfo=timezone.utc)


def test_fake_clock_sleep_does_not_block():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    c = FakeClock(start)
    t0 = time.time()
    c.sleep(3600)
    assert time.time() - t0 < 0.05
