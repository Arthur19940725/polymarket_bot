"""Composite-score ranker.

Selects top-N Polymarket traders by a weighted z-score of:
  - win_rate
  - total_pnl
  - sharpe_like (mean / std of per-market ROI)
"""
import logging
import statistics
import sys
from dataclasses import dataclass
from typing import Optional
from api_client import PolymarketAPI, Trade
from clock import Clock
from storage import Storage, TopTrader
from pnl_reconstructor import reconstruct, aggregate
from config import (
    RANK_WINDOW_DAYS, RANK_WEIGHTS, RANK_CANDIDATE_POOL_SIZE,
    MIN_RESOLVED_MARKETS, MIN_LIFETIME_VOLUME_USD, MIN_LAST_TRADE_DAYS,
    MIN_TOTAL_PNL_USD, MIN_WIN_RATE, RANK_SMOOTHING_DAYS,
)


@dataclass(frozen=True)
class RawMetrics:
    address: str
    resolved_count: int
    lifetime_volume: float
    last_trade_ts: int
    win_rate: float
    total_pnl: float
    sharpe_like: float


def _z_scores(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    mu = statistics.mean(values)
    sigma = statistics.pstdev(values)
    if sigma == 0:
        return [0.0] * len(values)
    return [(v - mu) / sigma for v in values]


class Ranker:
    def __init__(self, api: PolymarketAPI, clock: Clock,
                 storage: Optional[Storage] = None):
        self.api = api
        self.clock = clock
        self.storage = storage

    def _passes_filter(self, m: RawMetrics) -> bool:
        # Read from module to allow monkeypatching in tests
        ranker_module = sys.modules[__name__]
        min_markets = getattr(ranker_module, 'MIN_RESOLVED_MARKETS', MIN_RESOLVED_MARKETS)
        min_volume = getattr(ranker_module, 'MIN_LIFETIME_VOLUME_USD', MIN_LIFETIME_VOLUME_USD)
        min_days = getattr(ranker_module, 'MIN_LAST_TRADE_DAYS', MIN_LAST_TRADE_DAYS)
        min_pnl = getattr(ranker_module, 'MIN_TOTAL_PNL_USD', MIN_TOTAL_PNL_USD)
        min_winrate = getattr(ranker_module, 'MIN_WIN_RATE', MIN_WIN_RATE)

        if m.resolved_count < min_markets:
            return False
        if m.lifetime_volume < min_volume:
            return False
        now_ts = int(self.clock.now().timestamp())
        if now_ts - m.last_trade_ts > min_days * 86400:
            return False
        if m.total_pnl < min_pnl:
            return False
        if m.win_rate < min_winrate:
            return False
        return True

    def _compute_metrics(self, address: str) -> RawMetrics:
        # Cache check: same-day (date, addr) -> reuse last reconstruction.
        # Cache key is the UTC date string, so it naturally invalidates daily.
        date_str = self.clock.now().date().isoformat()
        if self.storage is not None:
            hit = self.storage.get_cached_metrics(date_str, address)
            if hit is not None:
                return RawMetrics(address=address, **hit)
        # Cache miss: fetch full paginated activity and reconstruct PnL.
        fetcher = getattr(self.api, "user_activity_all", None)
        if fetcher is not None:
            trades: list[Trade] = fetcher(address)
        else:
            trades = self.api.user_activity(address)
        market_pnls = reconstruct(trades)
        agg = aggregate(market_pnls, trades)
        if self.storage is not None:
            self.storage.save_cached_metrics(
                date=date_str, trader_addr=address,
                resolved_count=agg.resolved_count,
                lifetime_volume=agg.lifetime_volume,
                last_trade_ts=agg.last_trade_ts,
                win_rate=agg.win_rate,
                total_pnl=agg.total_pnl,
                sharpe_like=agg.sharpe_like,
            )
        return RawMetrics(
            address=address,
            resolved_count=agg.resolved_count,
            lifetime_volume=agg.lifetime_volume,
            last_trade_ts=agg.last_trade_ts,
            win_rate=agg.win_rate,
            total_pnl=agg.total_pnl,
            sharpe_like=agg.sharpe_like,
        )

    def compute_top_n(self, n: int = 10) -> list[TopTrader]:
        import time as _time
        date_str = self.clock.now().date().isoformat()
        candidates = self.api.leaderboard(limit=RANK_CANDIDATE_POOL_SIZE)
        metrics: list[RawMetrics] = []
        for c in candidates:
            try:
                metrics.append(self._compute_metrics(c.address))
            except Exception as exc:
                logging.warning("metrics failed for %s: %s", c.address, exc)
            _time.sleep(0.3)  # be polite to the API between candidates
        passing = [m for m in metrics if self._passes_filter(m)]
        if not passing:
            return []
        z_win = _z_scores([m.win_rate for m in passing])
        z_pnl = _z_scores([m.total_pnl for m in passing])
        z_sharpe = _z_scores([m.sharpe_like for m in passing])
        w1, w2, w3 = RANK_WEIGHTS
        scored = []
        for i, m in enumerate(passing):
            raw = w1 * z_win[i] + w2 * z_pnl[i] + w3 * z_sharpe[i]
            # Ordering uses a rolling average of this trader's raw scores over
            # the last RANK_SMOOTHING_DAYS, so a single hot/cold day doesn't
            # churn the top list. We persist the RAW score (not smoothed) so
            # tomorrow's average doesn't compound smoothing on smoothing.
            order_key = self._smoothed_score(m.address, raw)
            scored.append((order_key, raw, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:n]
        return [
            TopTrader(
                date=date_str, trader_addr=m.address, score=raw,
                win_rate=m.win_rate, total_pnl=m.total_pnl,
                sharpe_like=m.sharpe_like, rank=rank,
            )
            for rank, (_order, raw, m) in enumerate(top, start=1)
        ]

    def _smoothed_score(self, address: str, today_raw: float) -> float:
        days = getattr(sys.modules[__name__], "RANK_SMOOTHING_DAYS",
                       RANK_SMOOTHING_DAYS)
        if days <= 0 or self.storage is None:
            return today_raw
        from datetime import timedelta
        since = (self.clock.now().date()
                 - timedelta(days=days)).isoformat()
        history = self.storage.get_trader_scores_since(address, since)
        # history already includes any prior-day stored score; add today's raw
        # (today's row isn't persisted yet at this point).
        return (sum(history) + today_raw) / (len(history) + 1)

    def rank_and_persist(self, n: int = 10) -> list[TopTrader]:
        if self.storage is None:
            raise RuntimeError("storage required for persistence")
        top = self.compute_top_n(n)
        date_str = self.clock.now().date().isoformat()
        self.storage.save_top_10(date_str, top)
        return top
