"""Tests for the executor (DryRunExecutor)."""
from datetime import datetime, timezone
from api_client import FakeAPI
from clock import FakeClock
from storage import Storage, Position
from risk import RiskGate
from watcher import Event
from executor import DryRunExecutor


def _make_executor(tmp_db_path, prices=None, loss_limit=50.0):
    s = Storage(tmp_db_path)
    api = FakeAPI(leaderboard=[], activity_by_addr={}, prices=prices or {})
    clock = FakeClock(datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc))
    gate = RiskGate(storage=s, clock=clock, daily_loss_limit=loss_limit)
    ex = DryRunExecutor(storage=s, api=api, clock=clock, gate=gate,
                        copy_amount_usd=5.0, min_order_usd=1.0)
    return ex, s, api


def test_open_event_creates_position(tmp_db_path):
    ex, s, api = _make_executor(tmp_db_path,
                                prices={("m1", "YES"): 0.5})
    api.set_price("m1", "YES", 0.5)
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m1", side="YES", price=0.5,
                          timestamp=1747569300))
    open_pos = s.list_open_positions()
    assert len(open_pos) == 1
    assert open_pos[0].source_trader == "0xA"
    assert open_pos[0].market_id == "m1"
    assert open_pos[0].size_usd == 5.0


def test_open_logs_trade_with_dry_run_flag(tmp_db_path):
    ex, s, _ = _make_executor(tmp_db_path)
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m1", side="YES", price=0.5,
                          timestamp=1747569300))
    pos = s.list_open_positions()[0]
    trades = s.list_trades_for_position(pos.id)
    assert len(trades) == 1
    assert trades[0].action == "OPEN"
    assert trades[0].dry_run is True


def test_open_rejected_by_risk_gate(tmp_db_path):
    ex, s, _ = _make_executor(tmp_db_path, loss_limit=10.0)
    s.add_daily_pnl("2026-05-18", -15.0)  # already past limit
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m1", side="YES", price=0.5,
                          timestamp=1747569300))
    assert s.list_open_positions() == []


def test_open_skipped_when_already_holding(tmp_db_path):
    """Same source_trader + market + side → no duplicate open
    (spec §5: only follow first opening)."""
    ex, s, _ = _make_executor(tmp_db_path)
    e = Event(kind="OPEN", source_trader="0xA", market_id="m1",
              side="YES", price=0.5, timestamp=1747569300)
    ex.handle_event(e)
    ex.handle_event(e)
    assert len(s.list_open_positions()) == 1


def test_close_event_closes_matching_position(tmp_db_path):
    ex, s, api = _make_executor(tmp_db_path)
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m1", side="YES", price=0.4,
                          timestamp=1747569000))
    ex.handle_event(Event(kind="CLOSE", source_trader="0xA",
                          market_id="m1", side="YES", price=0.55,
                          timestamp=1747569300))
    open_pos = s.list_open_positions()
    assert open_pos == []
    import sqlite3
    conn = sqlite3.connect(tmp_db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM our_positions WHERE source_trader='0xA'"
                       ).fetchone()
    assert row["status"] == "MIRRORED_CLOSE"
    assert row["realized_pnl"] > 0


def test_close_without_matching_position_is_noop(tmp_db_path):
    ex, s, _ = _make_executor(tmp_db_path)
    ex.handle_event(Event(kind="CLOSE", source_trader="0xZ",
                          market_id="m999", side="YES", price=0.5,
                          timestamp=1747569300))
    assert s.list_open_positions() == []
