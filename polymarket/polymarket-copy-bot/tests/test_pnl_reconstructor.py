"""Tests for the PnL reconstructor."""
import json
import os
from api_client import _trade_from_raw
from pnl_reconstructor import reconstruct, aggregate


def _load_trades(fixtures_dir, name):
    with open(os.path.join(fixtures_dir, name)) as f:
        return [_trade_from_raw(r) for r in json.load(f)]


def test_reconstruct_two_round_trips_and_a_redeem(fixtures_dir):
    """alice fixture:
      m1: BUY 100@0.4 (cost 40) + SELL 100@0.6 (proceeds 60) -> PnL +20
      m2: BUY 100@0.5 (cost 50) + SELL 100@0.3 (proceeds 30) -> PnL -20
      m3: BUY 100@0.5 (cost 50) + REDEEM usdc 100 -> PnL +50
    """
    trades = _load_trades(fixtures_dir, "activity_alice.json")
    pnls = {m.market_id: m for m in reconstruct(trades)}
    assert pnls["m1"].realized_pnl == 20
    assert pnls["m1"].closed is True
    assert pnls["m2"].realized_pnl == -20
    assert pnls["m2"].closed is True
    assert pnls["m3"].realized_pnl == 50
    assert pnls["m3"].closed is True


def test_aggregate_alice(fixtures_dir):
    trades = _load_trades(fixtures_dir, "activity_alice.json")
    pnls = reconstruct(trades)
    agg = aggregate(pnls, trades)
    assert agg.resolved_count == 3
    # 2 wins (m1: +20, m3: +50), 1 loss (m2: -20)
    assert agg.win_rate == 2 / 3
    assert agg.total_pnl == 50
    # Lifetime volume = TRADE events only: 40+60+50+30+50 = 230
    assert agg.lifetime_volume == 230


def test_aggregate_bob_single_market(fixtures_dir):
    trades = _load_trades(fixtures_dir, "activity_bob.json")
    pnls = reconstruct(trades)
    agg = aggregate(pnls, trades)
    assert agg.resolved_count == 1
    assert agg.win_rate == 0.0  # bob lost
    assert agg.total_pnl == -10
    # sharpe = 0 since we only have 1 ROI sample
    assert agg.sharpe_like == 0.0


def test_reconstruct_ignores_reward_events():
    raw = [
        {"conditionId": "m1", "type": "REWARD", "side": "", "outcome": "",
         "size": 100, "usdcSize": 5, "price": 0, "timestamp": 1000},
    ]
    trades = [_trade_from_raw(r) for r in raw]
    pnls = reconstruct(trades)
    assert pnls == []  # no market_id from reward-only history? or empty


def test_reconstruct_unclosed_position_marked_open():
    """A BUY with no matching SELL/REDEEM should be flagged closed=False."""
    raw = [
        {"conditionId": "m1", "type": "TRADE", "side": "BUY", "outcome": "Yes",
         "size": 100, "usdcSize": 40, "price": 0.4, "timestamp": 1000},
    ]
    trades = [_trade_from_raw(r) for r in raw]
    pnls = reconstruct(trades)
    assert len(pnls) == 1
    assert pnls[0].closed is False
