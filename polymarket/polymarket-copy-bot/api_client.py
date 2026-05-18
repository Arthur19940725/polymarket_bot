"""Polymarket API client + fake implementation for tests.

Exposes a `PolymarketAPI` Protocol with three methods used by the bot.
`RequestsPolymarketAPI` hits real endpoints; `FakeAPI` reads fixtures.
"""
from dataclasses import dataclass
from typing import Protocol, Optional
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import config


@dataclass(frozen=True)
class LeaderboardEntry:
    address: str
    volume: float
    pnl: float


@dataclass(frozen=True)
class Trade:
    market_id: str
    side: str       # 'YES' | 'NO'
    type: str       # 'BUY' | 'SELL'
    size: float
    price: float
    timestamp: int  # unix seconds
    resolved: bool
    pnl_realized: Optional[float]


class PolymarketAPI(Protocol):
    def leaderboard(self, limit: int = 500) -> list[LeaderboardEntry]: ...
    def user_activity(self, address: str,
                      since_ts: Optional[int] = None) -> list[Trade]: ...
    def market_mid_price(self, market_id: str, side: str) -> float: ...


def _entry_from_raw(r: dict) -> LeaderboardEntry:
    return LeaderboardEntry(
        address=r["proxyWallet"],
        volume=float(r.get("volume", 0)),
        pnl=float(r.get("pnl", 0)),
    )


def _trade_from_raw(r: dict) -> Trade:
    return Trade(
        market_id=r["market"],
        side=r["side"],
        type=r["type"],
        size=float(r["size"]),
        price=float(r["price"]),
        timestamp=int(r["timestamp"]),
        resolved=bool(r.get("resolved", False)),
        pnl_realized=(
            float(r["pnl_realized"]) if r.get("pnl_realized") is not None
            else None
        ),
    )


class RequestsPolymarketAPI:
    """Real implementation. Endpoint paths are isolated here so a Polymarket
    schema change only touches this class."""

    def __init__(self, base_data_api: str = config.DATA_API,
                 base_clob_api: str = config.CLOB_API):
        self.data_api = base_data_api
        self.clob_api = base_clob_api

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=1, max=10))
    def _get(self, url: str, params: dict | None = None) -> list | dict:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def leaderboard(self, limit: int = 500) -> list[LeaderboardEntry]:
        raw = self._get(f"{self.data_api}/leaderboard",
                        params={"window": "all", "limit": limit})
        if isinstance(raw, dict) and "data" in raw:
            raw = raw["data"]
        return [_entry_from_raw(r) for r in raw]

    def user_activity(self, address: str,
                      since_ts: Optional[int] = None) -> list[Trade]:
        params = {"user": address, "limit": 500}
        if since_ts is not None:
            params["since"] = since_ts
        raw = self._get(f"{self.data_api}/activity", params=params)
        if isinstance(raw, dict) and "data" in raw:
            raw = raw["data"]
        return [_trade_from_raw(r) for r in raw]

    def market_mid_price(self, market_id: str, side: str) -> float:
        raw = self._get(f"{self.clob_api}/midpoint",
                        params={"market": market_id, "side": side})
        return float(raw["mid"]) if isinstance(raw, dict) else float(raw)


class FakeAPI:
    """In-memory fake for tests and backtest replay."""

    def __init__(self, leaderboard: list[dict],
                 activity_by_addr: dict[str, list[dict]],
                 prices: dict[tuple[str, str], float] | None = None):
        self._leaderboard = [_entry_from_raw(r) for r in leaderboard]
        self._activity = {
            addr: [_trade_from_raw(r) for r in trades]
            for addr, trades in activity_by_addr.items()
        }
        self._prices = prices or {}

    def leaderboard(self, limit: int = 500) -> list[LeaderboardEntry]:
        return self._leaderboard[:limit]

    def user_activity(self, address: str,
                      since_ts: Optional[int] = None) -> list[Trade]:
        trades = self._activity.get(address, [])
        if since_ts is not None:
            trades = [t for t in trades if t.timestamp >= since_ts]
        return list(trades)

    def market_mid_price(self, market_id: str, side: str) -> float:
        return self._prices.get((market_id, side), 0.5)

    # Test helpers — only used by tests
    def set_activity(self, address: str, trades: list[dict]) -> None:
        self._activity[address] = [_trade_from_raw(r) for r in trades]

    def set_price(self, market_id: str, side: str, price: float) -> None:
        self._prices[(market_id, side)] = price
