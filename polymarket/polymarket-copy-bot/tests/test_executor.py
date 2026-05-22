"""Tests for the executor (DryRunExecutor)."""
import pytest
from datetime import datetime, timezone
from api_client import FakeAPI
from clock import FakeClock
from storage import Storage, Position, TopTrader
from risk import RiskGate
from watcher import Event
from executor import DryRunExecutor, format_signal


def _make_executor(tmp_db_path, loss_limit=50.0):
    s = Storage(tmp_db_path)
    api = FakeAPI(leaderboard=[], activity_by_addr={})
    clock = FakeClock(datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc))
    gate = RiskGate(storage=s, clock=clock, daily_loss_limit=loss_limit)
    ex = DryRunExecutor(storage=s, api=api, clock=clock, gate=gate,
                        copy_amount_usd=5.0, min_order_usd=1.0)
    return ex, s, api


def test_open_event_creates_position(tmp_db_path):
    ex, s, api = _make_executor(tmp_db_path)
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


def test_format_signal_includes_url_and_trader_meta():
    """Signal output must be unambiguously actionable: market URL,
    trader rank/score, and the exact action to take."""
    e = Event(kind="OPEN", source_trader="0x6a72f61820abc",
              market_id="0xMARKET", side="Yes", price=0.4,
              timestamp=1779100000,
              token_id="tok_x", slug="atp-test-2026", title="ATP Test Match")
    meta = TopTrader(date="2026-05-22", trader_addr="0x6a72f61820abc",
                     score=1.025, win_rate=0.7941, total_pnl=640112.10,
                     sharpe_like=0.5, rank=1)
    s = format_signal(e, meta, copy_amount_usd=1.0)
    assert "SIGNAL" in s
    assert "polymarket.com/event/atp-test-2026" in s
    assert "ATP Test Match" in s
    assert "BUY" in s and "Yes" in s
    assert "rank #1" in s
    assert "79" in s  # win rate %
    assert "$1.00" in s
    assert "0.4" in s.replace("0.40", "0.4")  # price


def test_signal_emitted_on_open_event(tmp_db_path, capsys, caplog):
    """The DryRun OPEN flow must print the formatted signal to logs
    so the operator sees a clear action prompt."""
    import logging
    s = Storage(tmp_db_path)
    # Seed top_10 so the signal can include trader meta
    s.save_top_10("2026-05-22", [TopTrader(
        date="2026-05-22", trader_addr="0xA", score=0.8,
        win_rate=0.75, total_pnl=100000.0, sharpe_like=0.4, rank=1,
    )])
    api = FakeAPI(leaderboard=[], activity_by_addr={})
    clock = FakeClock(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc))
    gate = RiskGate(storage=s, clock=clock, daily_loss_limit=50)
    ex = DryRunExecutor(storage=s, api=api, clock=clock, gate=gate,
                        copy_amount_usd=1.0, min_order_usd=1.0)
    with caplog.at_level(logging.INFO):
        ex.handle_event(Event(
            kind="OPEN", source_trader="0xA",
            market_id="0xMARKET", side="Yes", price=0.4,
            timestamp=1779100000,
            slug="my-market-2026", title="My Market",
        ))
    text = caplog.text
    assert "SIGNAL" in text
    assert "polymarket.com/event/my-market-2026" in text


def test_signal_appended_to_jsonl(tmp_db_path, tmp_path):
    """Each SIGNAL is also appended to data/signals.jsonl as a structured
    record so tools/clip_latest_signal.py (and other downstream tools)
    can replay the operator queue without parsing logs."""
    import json
    s = Storage(tmp_db_path)
    s.save_top_10("2026-05-22", [TopTrader(
        date="2026-05-22", trader_addr="0xA", score=0.8,
        win_rate=0.75, total_pnl=100000.0, sharpe_like=0.4, rank=1,
    )])
    api = FakeAPI(leaderboard=[], activity_by_addr={})
    clock = FakeClock(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc))
    gate = RiskGate(storage=s, clock=clock, daily_loss_limit=50)
    signals_path = str(tmp_path / "signals.jsonl")
    ex = DryRunExecutor(storage=s, api=api, clock=clock, gate=gate,
                        copy_amount_usd=1.0, min_order_usd=1.0,
                        signals_jsonl_path=signals_path)
    ex.handle_event(Event(
        kind="OPEN", source_trader="0xA",
        market_id="0xMARKET", side="Yes", price=0.4,
        timestamp=1779100000,
        slug="my-market-2026", title="My Market",
    ))
    with open(signals_path) as f:
        lines = f.readlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["url"] == "https://polymarket.com/event/my-market-2026"
    assert rec["source_trader"] == "0xA"
    assert rec["side"] == "Yes"
    assert rec["price"] == 0.4
    assert rec["title"] == "My Market"
    assert rec["copy_amount_usd"] == 1.0


def test_signal_jsonl_default_path_is_none_skipped(tmp_db_path):
    """If signals_jsonl_path is None, the jsonl write is a no-op
    (backward compat with code that doesn't set this kwarg)."""
    s = Storage(tmp_db_path)
    api = FakeAPI(leaderboard=[], activity_by_addr={})
    clock = FakeClock(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc))
    gate = RiskGate(storage=s, clock=clock, daily_loss_limit=50)
    ex = DryRunExecutor(storage=s, api=api, clock=clock, gate=gate,
                        copy_amount_usd=1.0, min_order_usd=1.0)
    # Should not raise even without signals path
    ex.handle_event(Event(
        kind="OPEN", source_trader="0xA",
        market_id="0xMARKET", side="Yes", price=0.4,
        timestamp=1779100000,
        slug="my-market-2026", title="My Market",
    ))
    assert len(s.list_open_positions()) == 1


def test_resolve_event_marks_position_resolved_with_win_pnl(tmp_db_path):
    """When source REDEEMs, our matching position(s) flip to RESOLVED.
    Assumption: source only REDEEMs the winning outcome, and we mirrored
    their first BUY -> we also win -> realized_pnl = (1.0 - open_price) * shares."""
    ex, s, _ = _make_executor(tmp_db_path)
    # OPEN a position via the OPEN path first
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m1", side="Yes", price=0.4,
                          timestamp=1747569000))
    open_pos_before = s.list_open_positions()
    assert len(open_pos_before) == 1
    pid = open_pos_before[0].id
    # Source REDEEMs market
    ex.handle_event(Event(kind="RESOLVE", source_trader="0xA",
                          market_id="m1", side="",
                          price=0.0, timestamp=1747570000))
    # After RESOLVE, no OPEN positions for that market
    assert s.list_open_positions() == []
    closed = s.get_position_by_id(pid)
    assert closed.status == "RESOLVED"
    # size_usd=5, open_price=0.4 -> shares=12.5 -> win pnl = (1-0.4)*12.5 = 7.5
    assert closed.realized_pnl == pytest.approx(7.5)


def test_resolve_without_matching_position_is_noop(tmp_db_path):
    ex, s, _ = _make_executor(tmp_db_path)
    ex.handle_event(Event(kind="RESOLVE", source_trader="0xZ",
                          market_id="m999", side="",
                          price=0.0, timestamp=1747569300))
    assert s.list_open_positions() == []


def test_resolve_frees_g4_slot(tmp_db_path):
    """After RESOLVE, the source_trader can OPEN a new position even if
    they were previously at the G4 cap."""
    from risk import RiskGate
    from clock import FakeClock
    from storage import Storage
    s = Storage(tmp_db_path)
    api = FakeAPI(leaderboard=[], activity_by_addr={})
    clock = FakeClock(datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc))
    gate = RiskGate(storage=s, clock=clock, daily_loss_limit=1000,
                    max_open_positions=20, max_open_per_trader=1)
    ex = DryRunExecutor(storage=s, api=api, clock=clock, gate=gate,
                        copy_amount_usd=5.0, min_order_usd=1.0)
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m1", side="Yes", price=0.4,
                          timestamp=1747569000))
    # Cap is 1; trying second OPEN must be blocked
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m2", side="Yes", price=0.4,
                          timestamp=1747569100))
    assert len(s.list_open_positions()) == 1
    # RESOLVE frees the slot
    ex.handle_event(Event(kind="RESOLVE", source_trader="0xA",
                          market_id="m1", side="",
                          price=0.0, timestamp=1747569200))
    # Now another OPEN can land
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m3", side="Yes", price=0.4,
                          timestamp=1747569300))
    assert len(s.list_open_positions()) == 1
    open_now = s.list_open_positions()[0]
    assert open_now.market_id == "m3"
