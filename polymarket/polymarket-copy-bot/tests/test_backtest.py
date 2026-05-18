"""Tests for backtest engine."""
from datetime import datetime, timezone
from backtest import BacktestEngine
from api_client import FakeAPI
from clock import FakeClock
from storage import Storage


def test_backtest_replays_trades_in_order(tmp_db_path):
    """Two trades over time -> both mirrored, PnL accumulated."""
    raw = [
        {"market": "m1", "side": "YES", "type": "BUY", "size": 100,
         "price": 0.4, "timestamp": 1747000000, "resolved": False,
         "pnl_realized": None},
        {"market": "m1", "side": "YES", "type": "SELL", "size": 100,
         "price": 0.55, "timestamp": 1747000600, "resolved": False,
         "pnl_realized": None},
    ]
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": raw})
    storage = Storage(tmp_db_path)
    start = datetime.fromtimestamp(1746999000, tz=timezone.utc)
    clock = FakeClock(start)
    eng = BacktestEngine(
        api=api, storage=storage, clock=clock,
        top_addresses=["0xA"], copy_amount_usd=5.0, daily_loss_limit=50.0,
        poll_interval_sec=300, total_seconds=2000,
    )
    pnl, n_trades = eng.run()
    assert n_trades == 2
    assert pnl > 0


def test_backtest_respects_loss_limit(tmp_db_path):
    """Once limit breached, no new opens."""
    raw = [
        {"market": "m1", "side": "YES", "type": "BUY", "size": 100,
         "price": 0.5, "timestamp": 1747000000, "resolved": False,
         "pnl_realized": None},
        {"market": "m1", "side": "YES", "type": "SELL", "size": 100,
         "price": 0.1, "timestamp": 1747000600, "resolved": False,
         "pnl_realized": None},
        {"market": "m2", "side": "YES", "type": "BUY", "size": 100,
         "price": 0.5, "timestamp": 1747001200, "resolved": False,
         "pnl_realized": None},
    ]
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": raw})
    storage = Storage(tmp_db_path)
    start = datetime.fromtimestamp(1746999000, tz=timezone.utc)
    clock = FakeClock(start)
    eng = BacktestEngine(
        api=api, storage=storage, clock=clock,
        top_addresses=["0xA"], copy_amount_usd=5.0,
        daily_loss_limit=1.0,
        poll_interval_sec=300, total_seconds=3000,
    )
    pnl, n_trades = eng.run()
    assert n_trades == 2
    assert pnl < 0
