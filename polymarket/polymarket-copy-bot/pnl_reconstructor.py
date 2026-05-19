"""Reconstruct per-market PnL from Polymarket /activity event log.

Polymarket's public Data-API exposes raw events (TRADE BUY/SELL, REDEEM,
MERGE, REWARD) but no per-trade realized-PnL annotation. This module
walks a trader's full activity history and produces structured metrics
suitable for ranking.

A market is considered "closed" when one of:
  - the trader holds zero shares of every outcome they ever bought
    (achieved via SELL or MERGE), OR
  - a REDEEM event has been observed (market resolved)

For each closed market: PnL = USDC out - USDC in; ROI = PnL / USDC in.
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable
import statistics

from api_client import Trade


@dataclass(frozen=True)
class MarketPnl:
    market_id: str
    cost_basis: float
    proceeds: float
    realized_pnl: float
    roi: float           # realized_pnl / cost_basis (0 if cost_basis==0)
    closed: bool         # True if position fully exited or redeemed
    last_event_ts: int


@dataclass(frozen=True)
class AggregateMetrics:
    resolved_count: int   # number of closed markets
    win_rate: float
    total_pnl: float
    sharpe_like: float
    lifetime_volume: float
    last_trade_ts: int


def reconstruct(trades: Iterable[Trade]) -> list[MarketPnl]:
    """Walk events chronologically and produce per-market PnL records."""
    # Group by (market_id, outcome). A trader may hold both Yes+No on the
    # same market — those are independent positions until MERGE.
    by_market: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        if not t.market_id:
            continue
        if t.event_type == "REWARD":
            continue  # incentive income, not trading PnL
        by_market[t.market_id].append(t)

    out: list[MarketPnl] = []
    for market_id, events in by_market.items():
        events.sort(key=lambda e: e.timestamp)
        cost_basis = 0.0
        proceeds = 0.0
        shares_held: dict[str, float] = defaultdict(float)
        closed = False
        last_ts = 0
        for e in events:
            last_ts = max(last_ts, e.timestamp)
            if e.event_type == "TRADE":
                if e.action == "BUY":
                    cost_basis += e.usdc_size
                    shares_held[e.outcome] += e.size
                elif e.action == "SELL":
                    proceeds += e.usdc_size
                    shares_held[e.outcome] -= e.size
            elif e.event_type == "REDEEM":
                proceeds += e.usdc_size
                # REDEEM closes the entire market exposure
                for k in list(shares_held.keys()):
                    shares_held[k] = 0
                closed = True
            elif e.event_type == "MERGE":
                # Merging Yes+No outcomes redeems $1 per pair
                proceeds += e.usdc_size
                # Reduce shares evenly (each outcome contributes size)
                for k in list(shares_held.keys()):
                    shares_held[k] -= e.size
        if not closed:
            # If all per-outcome share counts are ~0, position is closed
            if all(abs(v) < 1e-6 for v in shares_held.values()):
                closed = True
        realized = proceeds - cost_basis
        roi = (realized / cost_basis) if cost_basis > 0 else 0.0
        out.append(MarketPnl(
            market_id=market_id, cost_basis=cost_basis, proceeds=proceeds,
            realized_pnl=realized, roi=roi, closed=closed,
            last_event_ts=last_ts,
        ))
    return out


def aggregate(market_pnls: list[MarketPnl],
              all_trades: Iterable[Trade]) -> AggregateMetrics:
    """Aggregate per-market PnL into the inputs the ranker expects."""
    closed = [m for m in market_pnls if m.closed and m.cost_basis > 0]
    wins = sum(1 for m in closed if m.realized_pnl > 0)
    total_pnl = sum(m.realized_pnl for m in closed)
    rois = [m.roi for m in closed]
    if len(rois) >= 2 and statistics.pstdev(rois) > 0:
        sharpe = statistics.mean(rois) / statistics.pstdev(rois)
    else:
        sharpe = 0.0
    trades_list = list(all_trades)
    lifetime_volume = sum(
        t.usdc_size for t in trades_list if t.event_type == "TRADE"
    )
    last_trade_ts = max((t.timestamp for t in trades_list), default=0)
    win_rate = (wins / len(closed)) if closed else 0.0
    return AggregateMetrics(
        resolved_count=len(closed),
        win_rate=win_rate,
        total_pnl=total_pnl,
        sharpe_like=sharpe,
        lifetime_volume=lifetime_volume,
        last_trade_ts=last_trade_ts,
    )
