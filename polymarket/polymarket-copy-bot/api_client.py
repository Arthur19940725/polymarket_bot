"""Polymarket API client + fake implementation for tests.

Real Polymarket endpoints (verified 2026-05-18):
  - lb-api.polymarket.com/profit?window=all  -> top traders by realized PnL
  - data-api.polymarket.com/activity?user=X  -> raw event log (TRADE/REDEEM/MERGE/REWARD)
  - data-api.polymarket.com/positions?user=X -> current open positions w/ realizedPnl
"""
import time
from dataclasses import dataclass
from typing import Protocol, Optional
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import config


@dataclass(frozen=True)
class LeaderboardEntry:
    address: str
    pnl: float        # realized profit in USD (from /profit?window=all)
    pseudonym: str = ""


@dataclass(frozen=True)
class Trade:
    """One Polymarket activity event. Fields mirror data-api /activity."""
    market_id: str       # conditionId
    token_id: str        # asset field -- the per-outcome CTF token ID
                         # (REQUIRED for CLOB orders; conditionId alone is not enough)
    event_type: str      # TRADE | REDEEM | MERGE | REWARD
    action: str          # BUY | SELL | '' (only set when event_type=TRADE)
    outcome: str         # 'Yes' | 'No' | candidate name | ''
    size: float          # share count
    usdc_size: float     # USDC value of the event
    price: float         # 0 for REDEEM/MERGE
    timestamp: int


@dataclass(frozen=True)
class Position:
    """Open position snapshot from /positions endpoint."""
    market_id: str
    outcome: str
    size: float
    avg_price: float
    initial_value: float
    current_value: float
    realized_pnl: float
    redeemable: bool


class PolymarketAPI(Protocol):
    def leaderboard(self, limit: int = 50) -> list[LeaderboardEntry]: ...
    def user_activity(self, address: str, limit: int = 500,
                      offset: int = 0) -> list[Trade]: ...
    def user_positions(self, address: str) -> list[Position]: ...


def _entry_from_raw(r: dict) -> LeaderboardEntry:
    return LeaderboardEntry(
        address=r["proxyWallet"],
        pnl=float(r.get("amount", 0)),
        pseudonym=str(r.get("pseudonym", "")),
    )


def _trade_from_raw(r: dict) -> Trade:
    return Trade(
        market_id=str(r.get("conditionId", "")),
        token_id=str(r.get("asset", "") or ""),
        event_type=str(r.get("type", "")),
        action=str(r.get("side", "") or ""),
        outcome=str(r.get("outcome", "") or ""),
        size=float(r.get("size", 0) or 0),
        usdc_size=float(r.get("usdcSize", 0) or 0),
        price=float(r.get("price", 0) or 0),
        timestamp=int(r.get("timestamp", 0)),
    )


def _position_from_raw(r: dict) -> Position:
    return Position(
        market_id=str(r.get("conditionId", "")),
        outcome=str(r.get("outcome", "")),
        size=float(r.get("size", 0)),
        avg_price=float(r.get("avgPrice", 0)),
        initial_value=float(r.get("initialValue", 0)),
        current_value=float(r.get("currentValue", 0)),
        realized_pnl=float(r.get("realizedPnl", 0)),
        redeemable=bool(r.get("redeemable", False)),
    )


_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class RequestsPolymarketAPI:
    """Real Polymarket API client. All URLs isolated here so a schema
    change requires touching only this class.

    Uses a persistent Session with a browser-like User-Agent to avoid
    Cloudflare rate-limit pages that target default Python UAs.
    """

    def __init__(self, data_api: str = config.DATA_API,
                 lb_api: str = config.LB_API):
        self.data_api = data_api
        self.lb_api = lb_api
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": _BROWSER_UA,
            "Accept": "application/json",
        })

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=1, max=10))
    def _get(self, url: str, params: dict | None = None):
        resp = self._session.get(url, params=params, timeout=15)
        if not resp.ok:
            import logging
            logging.warning("HTTP %s on %s params=%s body=%s",
                            resp.status_code, url, params, resp.text[:200])
            resp.raise_for_status()
        return resp.json()

    def leaderboard(self, limit: int = 50) -> list[LeaderboardEntry]:
        raw = self._get(f"{self.lb_api}/profit", params={"window": "all"})
        if isinstance(raw, dict) and "data" in raw:
            raw = raw["data"]
        return [_entry_from_raw(r) for r in raw[:limit]]

    def user_activity(self, address: str, limit: int = 500,
                      offset: int = 0) -> list[Trade]:
        raw = self._get(f"{self.data_api}/activity",
                        params={"user": address, "limit": limit,
                                "offset": offset})
        if isinstance(raw, dict) and "data" in raw:
            raw = raw["data"]
        return [_trade_from_raw(r) for r in raw]

    # Polymarket Data-API hard cap; offset > this returns HTTP 400.
    _MAX_API_OFFSET = 3000

    def user_activity_all(self, address: str,
                          page_size: int = 500,
                          max_records: int = 3000,
                          throttle_sec: float = 0.3) -> list[Trade]:
        """Paginated fetch of an address's full activity history.

        Capped at the smaller of (max_records, server's 3000-offset limit).
        A small throttle between page requests keeps Cloudflare happy.
        """
        limit_records = min(max_records, self._MAX_API_OFFSET)
        out: list[Trade] = []
        offset = 0
        while offset < limit_records:
            batch = self.user_activity(address, limit=page_size, offset=offset)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
            time.sleep(throttle_sec)
        return out

    def user_positions(self, address: str) -> list[Position]:
        raw = self._get(f"{self.data_api}/positions",
                        params={"user": address, "limit": 500})
        if isinstance(raw, dict) and "data" in raw:
            raw = raw["data"]
        return [_position_from_raw(r) for r in raw]


class FakeAPI:
    """In-memory fake for tests and backtest replay."""

    def __init__(self, leaderboard: list[dict],
                 activity_by_addr: dict[str, list[dict]],
                 positions_by_addr: dict[str, list[dict]] | None = None,
                 prices: dict[tuple[str, str], float] | None = None):
        self._leaderboard = [_entry_from_raw(r) for r in leaderboard]
        self._activity = {
            addr: [_trade_from_raw(r) for r in trades]
            for addr, trades in activity_by_addr.items()
        }
        self._positions = {
            addr: [_position_from_raw(r) for r in poses]
            for addr, poses in (positions_by_addr or {}).items()
        }
        self._prices = prices or {}

    def leaderboard(self, limit: int = 50) -> list[LeaderboardEntry]:
        return self._leaderboard[:limit]

    def user_activity(self, address: str, limit: int = 500,
                      offset: int = 0) -> list[Trade]:
        trades = self._activity.get(address, [])
        return trades[offset:offset + limit]

    def user_activity_all(self, address: str,
                          page_size: int = 500,
                          max_records: int = 5000) -> list[Trade]:
        return list(self._activity.get(address, []))[:max_records]

    def user_positions(self, address: str) -> list[Position]:
        return list(self._positions.get(address, []))

    # Test helpers
    def set_activity(self, address: str, trades: list[dict]) -> None:
        self._activity[address] = [_trade_from_raw(r) for r in trades]

    def set_positions(self, address: str, poses: list[dict]) -> None:
        self._positions[address] = [_position_from_raw(r) for r in poses]
