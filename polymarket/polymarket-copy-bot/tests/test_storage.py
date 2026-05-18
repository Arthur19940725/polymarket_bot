"""Tests for SQLite storage layer."""
import pytest
from datetime import datetime, timezone
from storage import Storage, Position, TradeRow, TopTrader


def test_init_creates_all_tables(tmp_db_path):
    s = Storage(tmp_db_path)
    tables = s.list_tables()
    assert set(tables) >= {"top_10", "our_positions", "trades", "daily_pnl"}


def test_save_and_load_top_10(tmp_db_path):
    s = Storage(tmp_db_path)
    today = "2026-05-18"
    entries = [
        TopTrader(date=today, trader_addr="0xA", score=1.5, win_rate=0.7,
                  total_pnl=1000.0, sharpe_like=2.1, rank=1),
        TopTrader(date=today, trader_addr="0xB", score=1.2, win_rate=0.6,
                  total_pnl=800.0, sharpe_like=1.9, rank=2),
    ]
    s.save_top_10(today, entries)
    got = s.load_top_10(today)
    assert len(got) == 2
    assert got[0].trader_addr == "0xA"
    assert got[1].rank == 2


def test_save_top_10_replaces_existing_date(tmp_db_path):
    s = Storage(tmp_db_path)
    today = "2026-05-18"
    s.save_top_10(today, [
        TopTrader(date=today, trader_addr="0xA", score=1.0, win_rate=0.5,
                  total_pnl=100, sharpe_like=1.0, rank=1)
    ])
    s.save_top_10(today, [
        TopTrader(date=today, trader_addr="0xB", score=2.0, win_rate=0.6,
                  total_pnl=200, sharpe_like=2.0, rank=1)
    ])
    got = s.load_top_10(today)
    assert len(got) == 1
    assert got[0].trader_addr == "0xB"


def test_insert_position_returns_id(tmp_db_path):
    s = Storage(tmp_db_path)
    pid = s.insert_position(Position(
        source_trader="0xA", market_id="m1", side="YES",
        size_usd=5.0, opened_at=datetime.now(timezone.utc).isoformat(),
        status="OPEN"
    ))
    assert isinstance(pid, int)
    assert pid > 0


def test_insert_position_unique_constraint(tmp_db_path):
    s = Storage(tmp_db_path)
    p = Position(source_trader="0xA", market_id="m1", side="YES",
                 size_usd=5.0, opened_at="2026-05-18T00:00:00+00:00",
                 status="OPEN")
    s.insert_position(p)
    with pytest.raises(Exception):
        s.insert_position(p)


def test_get_open_position_by_source(tmp_db_path):
    s = Storage(tmp_db_path)
    s.insert_position(Position(
        source_trader="0xA", market_id="m1", side="YES",
        size_usd=5.0, opened_at="2026-05-18T00:00:00+00:00", status="OPEN"
    ))
    got = s.get_open_position("0xA", "m1", "YES")
    assert got is not None
    assert got.size_usd == 5.0
    assert s.get_open_position("0xA", "m999", "YES") is None


def test_close_position_records_pnl(tmp_db_path):
    s = Storage(tmp_db_path)
    pid = s.insert_position(Position(
        source_trader="0xA", market_id="m1", side="YES",
        size_usd=5.0, opened_at="2026-05-18T00:00:00+00:00", status="OPEN"
    ))
    s.close_position(pid, closed_at="2026-05-18T01:00:00+00:00",
                     realized_pnl=1.5, new_status="MIRRORED_CLOSE")
    got = s.get_position_by_id(pid)
    assert got.status == "MIRRORED_CLOSE"
    assert got.realized_pnl == 1.5


def test_record_trade(tmp_db_path):
    s = Storage(tmp_db_path)
    pid = s.insert_position(Position(
        source_trader="0xA", market_id="m1", side="YES",
        size_usd=5.0, opened_at="2026-05-18T00:00:00+00:00", status="OPEN"
    ))
    s.record_trade(TradeRow(
        position_id=pid, action="OPEN", price=0.45, size=11.1,
        tx_hash=None, ts="2026-05-18T00:00:00+00:00", dry_run=True
    ))
    trades = s.list_trades_for_position(pid)
    assert len(trades) == 1
    assert trades[0].action == "OPEN"
    assert trades[0].dry_run is True


def test_daily_pnl_accumulate(tmp_db_path):
    s = Storage(tmp_db_path)
    s.add_daily_pnl("2026-05-18", 5.0)
    s.add_daily_pnl("2026-05-18", -2.0)
    assert s.get_daily_pnl("2026-05-18") == 3.0
    assert s.get_daily_pnl("2026-05-19") == 0.0


def test_set_and_check_halted(tmp_db_path):
    s = Storage(tmp_db_path)
    assert s.is_halted("2026-05-18") is False
    s.mark_halted("2026-05-18", "2026-05-18T15:00:00+00:00")
    assert s.is_halted("2026-05-18") is True
