"""Tests for the daily-loss risk gate."""
from datetime import datetime, timezone
from clock import FakeClock
from storage import Storage
from risk import RiskGate


def test_allows_open_when_below_limit(tmp_db_path):
    s = Storage(tmp_db_path)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    assert g.allow_open() is True


def test_blocks_open_when_at_limit(tmp_db_path):
    s = Storage(tmp_db_path)
    s.add_daily_pnl("2026-05-18", -50.0)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    assert g.allow_open() is False


def test_blocks_open_when_over_limit(tmp_db_path):
    s = Storage(tmp_db_path)
    s.add_daily_pnl("2026-05-18", -75.0)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    assert g.allow_open() is False


def test_always_allows_close(tmp_db_path):
    s = Storage(tmp_db_path)
    s.add_daily_pnl("2026-05-18", -200.0)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    assert g.allow_close() is True


def test_record_pnl_writes_storage(tmp_db_path):
    s = Storage(tmp_db_path)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    g.record_realized_pnl(-10.0)
    g.record_realized_pnl(-15.0)
    assert s.get_daily_pnl("2026-05-18") == -25.0


def test_halt_persisted_after_breach(tmp_db_path):
    s = Storage(tmp_db_path)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    g.record_realized_pnl(-60.0)
    g.allow_open()  # triggers halt-marker
    assert s.is_halted("2026-05-18") is True


def test_day_rollover_resets_check(tmp_db_path):
    s = Storage(tmp_db_path)
    s.add_daily_pnl("2026-05-18", -100.0)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 19, tzinfo=timezone.utc)), daily_loss_limit=50)
    assert g.allow_open() is True
