"""Tests for ranker."""
import json
import os
import pytest
from datetime import datetime, timezone
from api_client import FakeAPI
from clock import FakeClock
from ranker import Ranker, RawMetrics, _z_scores


def _load(fixtures_dir, name):
    with open(os.path.join(fixtures_dir, name)) as f:
        return json.load(f)


def test_z_scores_zero_when_all_equal():
    z = _z_scores([5.0, 5.0, 5.0])
    assert all(v == 0.0 for v in z)


def test_z_scores_standard():
    z = _z_scores([1.0, 2.0, 3.0])
    assert z[1] == pytest.approx(0.0, abs=1e-6)
    assert z[0] < 0 and z[2] > 0


def test_filter_rejects_low_sample_count():
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    metrics = RawMetrics(
        address="0xX", resolved_count=10, lifetime_volume=5000,
        last_trade_ts=int(datetime(2026, 5, 17, tzinfo=timezone.utc).timestamp()),
        win_rate=0.9, total_pnl=1000, sharpe_like=2.0,
    )
    assert r._passes_filter(metrics) is False


def test_filter_rejects_low_volume():
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    metrics = RawMetrics(
        address="0xX", resolved_count=50, lifetime_volume=500,
        last_trade_ts=int(datetime(2026, 5, 17, tzinfo=timezone.utc).timestamp()),
        win_rate=0.9, total_pnl=1000, sharpe_like=2.0,
    )
    assert r._passes_filter(metrics) is False


def test_filter_rejects_stale_trader():
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(now))
    metrics = RawMetrics(
        address="0xX", resolved_count=50, lifetime_volume=5000,
        last_trade_ts=int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp()),
        win_rate=0.9, total_pnl=1000, sharpe_like=2.0,
    )
    assert r._passes_filter(metrics) is False


def test_filter_passes_good_candidate():
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(now))
    metrics = RawMetrics(
        address="0xX", resolved_count=50, lifetime_volume=5000,
        last_trade_ts=int(datetime(2026, 5, 17, tzinfo=timezone.utc).timestamp()),
        win_rate=0.6, total_pnl=2000, sharpe_like=1.5,
    )
    assert r._passes_filter(metrics) is True


def test_filter_rejects_negative_total_pnl():
    """Absolute floor: only positive-PnL traders qualify, regardless of
    other metrics. Reason: spec is 'follow the best traders'; losing
    traders should never appear, even if z-score would rank them."""
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(now))
    metrics = RawMetrics(
        address="0xX", resolved_count=100, lifetime_volume=50000,
        last_trade_ts=int(datetime(2026, 5, 17, tzinfo=timezone.utc).timestamp()),
        win_rate=0.55, total_pnl=-100.0, sharpe_like=0.3,
    )
    assert r._passes_filter(metrics) is False


def test_filter_rejects_low_win_rate():
    """Absolute floor: 50% win rate minimum."""
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(now))
    metrics = RawMetrics(
        address="0xX", resolved_count=100, lifetime_volume=50000,
        last_trade_ts=int(datetime(2026, 5, 17, tzinfo=timezone.utc).timestamp()),
        win_rate=0.40, total_pnl=10000.0, sharpe_like=0.2,
    )
    assert r._passes_filter(metrics) is False


def test_compute_metrics_from_activity(fixtures_dir):
    """alice has 3 closed markets:
       m1 round-trip: +20
       m2 round-trip: -20
       m3 redeem:     +50
       Total +50, 2/3 win, lifetime volume 230 (TRADE events only)."""
    api = FakeAPI(
        leaderboard=_load(fixtures_dir, "leaderboard.json"),
        activity_by_addr={
            "0xAlice": _load(fixtures_dir, "activity_alice.json"),
        },
    )
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    r = Ranker(api=api, clock=FakeClock(now))
    m = r._compute_metrics("0xAlice")
    assert m.resolved_count == 3
    assert m.win_rate == pytest.approx(2 / 3)
    assert m.total_pnl == 50
    assert m.lifetime_volume == 230


def test_rank_end_to_end(fixtures_dir, monkeypatch):
    api = FakeAPI(
        leaderboard=_load(fixtures_dir, "leaderboard.json"),
        activity_by_addr={
            "0xAlice": _load(fixtures_dir, "activity_alice.json"),
            "0xBob": _load(fixtures_dir, "activity_bob.json"),
        },
    )
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    monkeypatch.setattr("ranker.MIN_RESOLVED_MARKETS", 1)
    monkeypatch.setattr("ranker.MIN_LIFETIME_VOLUME_USD", 0)
    monkeypatch.setattr("ranker.MIN_LAST_TRADE_DAYS", 1000)
    r = Ranker(api=api, clock=FakeClock(now))
    top = r.compute_top_n(n=2)
    assert len(top) >= 1
    assert top[0].trader_addr in ("0xAlice", "0xBob")
    if len(top) == 2:
        assert top[0].trader_addr == "0xAlice"
        assert top[0].rank == 1
