"""Tests for the daily-loss risk gate."""
from datetime import datetime, timezone
from clock import FakeClock
from storage import Storage, Position
from risk import RiskGate


def _open(s: Storage, addr: str, market: str, side: str = "Yes") -> int:
    return s.insert_position(Position(
        source_trader=addr, market_id=market, side=side,
        size_usd=5.0, opened_at="2026-05-18T00:00:00+00:00",
        status="OPEN",
    ))


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


def test_blocks_open_at_max_open_positions(tmp_db_path):
    """G3: cap on simultaneous OPEN positions across all source_traders."""
    s = Storage(tmp_db_path)
    for i in range(3):
        _open(s, "0xA", f"m{i}")
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)),
        daily_loss_limit=1000, max_open_positions=3)
    assert g.allow_open() is False


def test_allows_open_below_max_positions(tmp_db_path):
    s = Storage(tmp_db_path)
    for i in range(2):
        _open(s, "0xA", f"m{i}")
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)),
        daily_loss_limit=1000, max_open_positions=3)
    assert g.allow_open() is True


def test_closing_a_position_reopens_room(tmp_db_path):
    """Once a position is closed, the slot frees up."""
    s = Storage(tmp_db_path)
    pids = [_open(s, "0xA", f"m{i}") for i in range(3)]
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)),
        daily_loss_limit=1000, max_open_positions=3)
    assert g.allow_open() is False
    s.close_position(pids[0], closed_at="2026-05-18T01:00:00+00:00",
                     realized_pnl=0, new_status="MIRRORED_CLOSE")
    assert g.allow_open() is True


def test_max_positions_does_not_block_close(tmp_db_path):
    s = Storage(tmp_db_path)
    for i in range(5):
        _open(s, "0xA", f"m{i}")
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)),
        daily_loss_limit=1000, max_open_positions=3)
    assert g.allow_close() is True


def test_g4_blocks_when_single_trader_hits_per_trader_cap(tmp_db_path):
    """G4: even if G3 has room, a single source_trader can't exceed
    max_open_per_trader."""
    s = Storage(tmp_db_path)
    for i in range(3):
        _open(s, "0xA", f"m{i}")
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)),
        daily_loss_limit=1000, max_open_positions=20,
        max_open_per_trader=3)
    assert g.allow_open(source_trader="0xA") is False
    # Other traders should still be allowed
    assert g.allow_open(source_trader="0xB") is True


def test_g4_disabled_when_param_none(tmp_db_path):
    s = Storage(tmp_db_path)
    for i in range(10):
        _open(s, "0xA", f"m{i}")
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)),
        daily_loss_limit=1000, max_open_positions=20)  # no per-trader
    assert g.allow_open(source_trader="0xA") is True


def test_g4_without_trader_arg_falls_back_to_global_check(tmp_db_path):
    """If caller does not pass source_trader, G4 cannot enforce; G3 still works."""
    s = Storage(tmp_db_path)
    for i in range(2):
        _open(s, "0xA", f"m{i}")
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)),
        daily_loss_limit=1000, max_open_positions=10,
        max_open_per_trader=1)
    assert g.allow_open() is True  # legacy call still works
