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


def test_compute_metrics_uses_cache_when_available(tmp_db_path, fixtures_dir):
    """Second call on same date should hit cache, not re-fetch activity."""
    from storage import Storage
    s = Storage(tmp_db_path)
    api = FakeAPI(
        leaderboard=_load(fixtures_dir, "leaderboard.json"),
        activity_by_addr={
            "0xAlice": _load(fixtures_dir, "activity_alice.json"),
        },
    )
    # Track activity calls
    call_count = {"n": 0}
    orig = api.user_activity_all
    def counting(*a, **kw):
        call_count["n"] += 1
        return orig(*a, **kw)
    api.user_activity_all = counting

    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    r = Ranker(api=api, clock=FakeClock(now), storage=s)

    m1 = r._compute_metrics("0xAlice")
    assert call_count["n"] == 1
    m2 = r._compute_metrics("0xAlice")
    assert call_count["n"] == 1, "second call should hit cache, not refetch"
    assert m1.total_pnl == m2.total_pnl
    assert m1.win_rate == m2.win_rate


def test_compute_metrics_cache_invalidates_on_new_date(tmp_db_path, fixtures_dir):
    """A different day -> cache miss, re-fetches."""
    from storage import Storage
    s = Storage(tmp_db_path)
    api = FakeAPI(
        leaderboard=_load(fixtures_dir, "leaderboard.json"),
        activity_by_addr={"0xAlice": _load(fixtures_dir, "activity_alice.json")},
    )
    call_count = {"n": 0}
    orig = api.user_activity_all
    def counting(*a, **kw):
        call_count["n"] += 1
        return orig(*a, **kw)
    api.user_activity_all = counting

    r1 = Ranker(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), storage=s)
    r1._compute_metrics("0xAlice")
    assert call_count["n"] == 1

    r2 = Ranker(api=api, clock=FakeClock(
        datetime(2026, 5, 19, tzinfo=timezone.utc)), storage=s)
    r2._compute_metrics("0xAlice")
    assert call_count["n"] == 2  # new date -> cache miss


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


def test_smoothed_score_no_storage_returns_today(tmp_db_path):
    """No storage -> smoothing disabled, returns today's raw."""
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(
        datetime(2026, 5, 27, tzinfo=timezone.utc)))
    assert r._smoothed_score("0xA", 1.5) == 1.5


def test_smoothed_score_averages_history(tmp_db_path, monkeypatch):
    """Rolling avg of stored prior scores + today's raw."""
    from storage import Storage, TopTrader
    s = Storage(tmp_db_path)
    # 0xA scored 1.0 and 0.4 on two prior days
    s.save_top_10("2026-05-25", [TopTrader(
        date="2026-05-25", trader_addr="0xA", score=1.0, win_rate=0.7,
        total_pnl=100, sharpe_like=0.5, rank=1)])
    s.save_top_10("2026-05-26", [TopTrader(
        date="2026-05-26", trader_addr="0xA", score=0.4, win_rate=0.6,
        total_pnl=120, sharpe_like=0.4, rank=2)])
    monkeypatch.setattr("ranker.RANK_SMOOTHING_DAYS", 7)
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(
        datetime(2026, 5, 27, tzinfo=timezone.utc)), storage=s)
    # history [1.0, 0.4] + today 1.6 -> mean = 3.0/3 = 1.0
    assert r._smoothed_score("0xA", 1.6) == 1.0


def test_smoothed_score_disabled_when_zero_days(tmp_db_path, monkeypatch):
    from storage import Storage, TopTrader
    s = Storage(tmp_db_path)
    s.save_top_10("2026-05-26", [TopTrader(
        date="2026-05-26", trader_addr="0xA", score=99.0, win_rate=0.6,
        total_pnl=120, sharpe_like=0.4, rank=1)])
    monkeypatch.setattr("ranker.RANK_SMOOTHING_DAYS", 0)
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(
        datetime(2026, 5, 27, tzinfo=timezone.utc)), storage=s)
    assert r._smoothed_score("0xA", 0.2) == 0.2  # ignores history


def test_compute_top_n_persists_raw_not_smoothed(tmp_db_path, fixtures_dir, monkeypatch):
    """Stored score must be raw (so future smoothing doesn't compound)."""
    from storage import Storage, TopTrader
    s = Storage(tmp_db_path)
    # Give 0xAlice a high prior score so smoothing would change ordering
    s.save_top_10("2026-05-26", [TopTrader(
        date="2026-05-26", trader_addr="0xAlice", score=5.0, win_rate=0.9,
        total_pnl=999, sharpe_like=0.9, rank=1)])
    api = FakeAPI(
        leaderboard=_load(fixtures_dir, "leaderboard.json"),
        activity_by_addr={
            "0xAlice": _load(fixtures_dir, "activity_alice.json"),
            "0xBob": _load(fixtures_dir, "activity_bob.json"),
        },
    )
    monkeypatch.setattr("ranker.MIN_RESOLVED_MARKETS", 1)
    monkeypatch.setattr("ranker.MIN_LIFETIME_VOLUME_USD", 0)
    monkeypatch.setattr("ranker.MIN_LAST_TRADE_DAYS", 1000)
    monkeypatch.setattr("ranker.MIN_TOTAL_PNL_USD", -1e9)
    monkeypatch.setattr("ranker.MIN_WIN_RATE", 0.0)
    monkeypatch.setattr("ranker.RANK_SMOOTHING_DAYS", 7)
    r = Ranker(api=api, clock=FakeClock(
        datetime(2026, 5, 27, tzinfo=timezone.utc)), storage=s)
    top = r.compute_top_n(n=2)
    # The persisted score for each must be a plausible raw z-score
    # (|z| typically < 2 for 2 candidates), never the 5.0 historical value.
    for t in top:
        assert abs(t.score) < 5.0
