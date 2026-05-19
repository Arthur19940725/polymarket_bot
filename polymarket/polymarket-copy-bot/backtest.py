"""Backtest engine.

Replays historical activity through the SAME Watcher -> RiskGate -> Executor
path used in live mode. Time is virtual (FakeClock). API is FakeAPI seeded
with full historical data.
"""
import sqlite3
from typing import Optional
from api_client import FakeAPI, PolymarketAPI, Trade
from clock import FakeClock
from storage import Storage
from risk import RiskGate
from watcher import Watcher
from executor import DryRunExecutor


class _TimeFilteredAPI:
    """Wraps a FakeAPI so user_activity only returns trades with
    timestamp <= current virtual clock. Lets a single seeded FakeAPI
    simulate trades appearing over backtest time."""

    def __init__(self, inner: PolymarketAPI, clock: FakeClock):
        self._inner = inner
        self._clock = clock

    def leaderboard(self, limit: int = 50):
        return self._inner.leaderboard(limit=limit)

    def user_activity(self, address: str, limit: int = 500,
                      offset: int = 0) -> list[Trade]:
        trades = self._inner.user_activity(address, limit=limit, offset=offset)
        cutoff = int(self._clock.now().timestamp())
        return [t for t in trades if t.timestamp <= cutoff]

    def user_activity_all(self, address: str, page_size: int = 500,
                          max_records: int = 5000) -> list[Trade]:
        trades = self._inner.user_activity_all(
            address, page_size=page_size, max_records=max_records)
        cutoff = int(self._clock.now().timestamp())
        return [t for t in trades if t.timestamp <= cutoff]

    def user_positions(self, address: str):
        return self._inner.user_positions(address)


class BacktestEngine:
    def __init__(self, api: PolymarketAPI, storage: Storage, clock: FakeClock,
                 top_addresses: list[str], copy_amount_usd: float,
                 daily_loss_limit: float, poll_interval_sec: int,
                 total_seconds: int):
        self.api = _TimeFilteredAPI(api, clock)
        self.storage = storage
        self.clock = clock
        self.top_addresses = top_addresses
        self.poll_interval = poll_interval_sec
        self.total_seconds = total_seconds
        self.gate = RiskGate(storage=storage, clock=clock,
                             daily_loss_limit=daily_loss_limit)
        self.watcher = Watcher(api=self.api, clock=clock)
        self.executor = DryRunExecutor(
            storage=storage, api=self.api, clock=clock, gate=self.gate,
            copy_amount_usd=copy_amount_usd, min_order_usd=1.0,
        )

    def run(self) -> tuple[float, int]:
        elapsed = 0
        while elapsed < self.total_seconds:
            events = self.watcher.poll(self.top_addresses)
            for ev in events:
                self.executor.handle_event(ev)
            self.clock.sleep(self.poll_interval)
            elapsed += self.poll_interval
        conn = sqlite3.connect(self.storage.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT realized_pnl FROM our_positions "
            "WHERE realized_pnl IS NOT NULL"
        ).fetchall()
        total_pnl = sum(r["realized_pnl"] for r in rows)
        n_trades = conn.execute(
            "SELECT COUNT(*) AS c FROM trades"
        ).fetchone()["c"]
        return total_pnl, n_trades


def run_backtest(days: int, db_path: str = ":memory:") -> tuple[float, int]:
    """Convenience wrapper invoked by `main.py backtest`."""
    from datetime import datetime, timezone, timedelta
    from api_client import RequestsPolymarketAPI
    real_api = RequestsPolymarketAPI()
    real_storage = Storage("data/bot.sqlite")
    today = datetime.now(timezone.utc).date().isoformat()
    top = real_storage.load_top_10(today)
    if not top:
        raise RuntimeError(
            "No top_10 found for today - run `main.py rank` first."
        )
    since_ts = int((datetime.now(timezone.utc)
                    - timedelta(days=days)).timestamp())
    activity_by_addr = {}
    for t in top:
        trades = real_api.user_activity(t.trader_addr, since_ts=since_ts)
        activity_by_addr[t.trader_addr] = [
            {
                "market": tr.market_id, "side": tr.side, "type": tr.type,
                "size": tr.size, "price": tr.price,
                "timestamp": tr.timestamp, "resolved": tr.resolved,
                "pnl_realized": tr.pnl_realized,
            }
            for tr in trades
        ]
    fake_api = FakeAPI(leaderboard=[], activity_by_addr=activity_by_addr)
    start = datetime.fromtimestamp(since_ts, tz=timezone.utc)
    clock = FakeClock(start)
    bt_storage = Storage(db_path)
    eng = BacktestEngine(
        api=fake_api, storage=bt_storage, clock=clock,
        top_addresses=[t.trader_addr for t in top],
        copy_amount_usd=5.0, daily_loss_limit=50.0,
        poll_interval_sec=300, total_seconds=days * 86400,
    )
    return eng.run()
