"""Tests for tools/daily_report.py - the daily Markdown report."""
import json
from datetime import datetime, timezone
import sys
import os

# Tools dir not on sys.path by default
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from storage import Storage, Position, TopTrader
import daily_report as dr


def _seed_signals(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_empty_inputs_produce_no_signals_section(tmp_path, tmp_db_path):
    Storage(tmp_db_path)  # init schema
    sigs_path = str(tmp_path / "signals.jsonl")
    open(sigs_path, "w").close()  # empty file
    md = dr.build_report(date="2026-05-23", db_path=tmp_db_path,
                         signals_path=sigs_path)
    assert "2026-05-23" in md
    assert "0 signals" in md
    assert "$0.00" in md  # realized pnl


def test_signals_grouped_by_trader(tmp_path, tmp_db_path):
    Storage(tmp_db_path)
    sigs_path = str(tmp_path / "signals.jsonl")
    _seed_signals(sigs_path, [
        {"ts": "2026-05-23T08:00:00+00:00", "source_trader": "0xA",
         "rank": 1, "win_rate": 0.8, "total_pnl": 100000,
         "title": "Market A", "slug": "a-2026", "side": "Yes",
         "price": 0.4, "url": "https://polymarket.com/event/a-2026",
         "market_id": "m1"},
        {"ts": "2026-05-23T09:00:00+00:00", "source_trader": "0xA",
         "rank": 1, "win_rate": 0.8, "total_pnl": 100000,
         "title": "Market B", "slug": "b-2026", "side": "No",
         "price": 0.3, "url": "https://polymarket.com/event/b-2026",
         "market_id": "m2"},
        {"ts": "2026-05-23T10:00:00+00:00", "source_trader": "0xB",
         "rank": 2, "win_rate": 0.7, "total_pnl": 50000,
         "title": "Market C", "slug": "c-2026", "side": "Over",
         "price": 0.6, "url": "https://polymarket.com/event/c-2026",
         "market_id": "m3"},
        # signal from a different day - should be excluded
        {"ts": "2026-05-22T08:00:00+00:00", "source_trader": "0xA",
         "rank": 1, "win_rate": 0.8, "total_pnl": 100000,
         "title": "Old Market", "slug": "old", "side": "Yes",
         "price": 0.5, "url": "https://polymarket.com/event/old",
         "market_id": "m_old"},
    ])
    md = dr.build_report(date="2026-05-23", db_path=tmp_db_path,
                         signals_path=sigs_path)
    assert "3 signals" in md  # 3 from 2026-05-23, not the May-22 one
    assert "Market A" in md
    assert "Market C" in md
    assert "Old Market" not in md
    # Trader 0xA contributed 2, 0xB contributed 1
    assert "0xA" in md and "0xB" in md


def test_realized_pnl_section(tmp_path, tmp_db_path):
    s = Storage(tmp_db_path)
    # Two positions resolved today (2026-05-23): one win, one ~breakeven
    pid1 = s.insert_position(Position(
        source_trader="0xA", market_id="m1", side="Yes",
        size_usd=1.0, opened_at="2026-05-22T10:00:00+00:00",
        status="OPEN"))
    s.close_position(pid1, closed_at="2026-05-23T15:00:00+00:00",
                     realized_pnl=2.50, new_status="RESOLVED")
    pid2 = s.insert_position(Position(
        source_trader="0xA", market_id="m2", side="No",
        size_usd=1.0, opened_at="2026-05-22T11:00:00+00:00",
        status="OPEN"))
    s.close_position(pid2, closed_at="2026-05-23T16:00:00+00:00",
                     realized_pnl=0.20, new_status="RESOLVED")
    # one OPEN still standing
    s.insert_position(Position(
        source_trader="0xA", market_id="m3", side="Yes",
        size_usd=1.0, opened_at="2026-05-23T09:00:00+00:00",
        status="OPEN"))
    sigs_path = str(tmp_path / "signals.jsonl")
    open(sigs_path, "w").close()
    md = dr.build_report(date="2026-05-23", db_path=tmp_db_path,
                         signals_path=sigs_path)
    assert "$2.70" in md  # 2.50 + 0.20
    assert "2 resolved" in md
    assert "1 still open" in md


def test_rank_diff_vs_previous_day(tmp_path, tmp_db_path):
    s = Storage(tmp_db_path)
    s.save_top_10("2026-05-22", [
        TopTrader(date="2026-05-22", trader_addr="0xA", score=1.0,
                  win_rate=0.8, total_pnl=100000, sharpe_like=0.5, rank=1),
        TopTrader(date="2026-05-22", trader_addr="0xB", score=0.5,
                  win_rate=0.6, total_pnl=50000, sharpe_like=0.3, rank=2),
    ])
    s.save_top_10("2026-05-23", [
        # 0xB rises, 0xA falls, 0xC is new
        TopTrader(date="2026-05-23", trader_addr="0xC", score=1.2,
                  win_rate=0.9, total_pnl=200000, sharpe_like=0.6, rank=1),
        TopTrader(date="2026-05-23", trader_addr="0xB", score=0.8,
                  win_rate=0.7, total_pnl=60000, sharpe_like=0.4, rank=2),
    ])
    sigs_path = str(tmp_path / "signals.jsonl")
    open(sigs_path, "w").close()
    md = dr.build_report(date="2026-05-23", db_path=tmp_db_path,
                         signals_path=sigs_path)
    assert "NEW" in md  # 0xC entered
    assert "DROPPED" in md  # 0xA left
    assert "0xC" in md and "0xA" in md
