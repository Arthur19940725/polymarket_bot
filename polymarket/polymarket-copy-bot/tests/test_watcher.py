"""Tests for watcher."""
import json
import os
from datetime import datetime, timezone
from api_client import FakeAPI
from clock import FakeClock
from watcher import Watcher, Event


def _load(fixtures_dir, name):
    with open(os.path.join(fixtures_dir, name)) as f:
        return json.load(f)


def test_first_poll_emits_no_events(fixtures_dir):
    """First poll establishes baseline; nothing is 'new'."""
    api = FakeAPI(
        leaderboard=[],
        activity_by_addr={"0xAlice": _load(fixtures_dir, "activity_alice.json")},
    )
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    events = w.poll(top_addresses=["0xAlice"])
    assert events == []


def test_second_poll_detects_new_open(fixtures_dir):
    api = FakeAPI(
        leaderboard=[],
        activity_by_addr={"0xAlice": _load(fixtures_dir, "activity_alice.json")},
    )
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    w.poll(top_addresses=["0xAlice"])  # baseline
    api.set_activity("0xAlice", _load(fixtures_dir, "activity_alice_t2.json"))
    events = w.poll(top_addresses=["0xAlice"])
    assert len(events) == 1
    e = events[0]
    assert e.kind == "OPEN"
    assert e.source_trader == "0xAlice"
    assert e.market_id == "m9"
    assert e.side == "Yes"
    assert e.price == 0.45


def test_detects_close_when_position_disappears():
    """If a trader holds a position then exits, watcher emits CLOSE."""
    initial = [{
        "conditionId": "mX", "type": "TRADE", "side": "BUY", "outcome": "Yes",
        "size": 100, "usdcSize": 40, "price": 0.4, "timestamp": 1747569000,
    }]
    after = initial + [{
        "conditionId": "mX", "type": "TRADE", "side": "SELL", "outcome": "Yes",
        "size": 100, "usdcSize": 55, "price": 0.55, "timestamp": 1747569300,
    }]
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": initial})
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    w.poll(top_addresses=["0xA"])
    api.set_activity("0xA", after)
    events = w.poll(top_addresses=["0xA"])
    assert len(events) == 1
    assert events[0].kind == "CLOSE"
    assert events[0].market_id == "mX"
    assert events[0].price == 0.55


def test_close_ignored_when_trader_not_in_top10():
    """E1 rule: trader dropped from top 10 -> ignore their exits."""
    initial = [{
        "conditionId": "mX", "type": "TRADE", "side": "BUY", "outcome": "Yes",
        "size": 100, "usdcSize": 40, "price": 0.4, "timestamp": 1747569000,
    }]
    after = initial + [{
        "conditionId": "mX", "type": "TRADE", "side": "SELL", "outcome": "Yes",
        "size": 100, "usdcSize": 55, "price": 0.55, "timestamp": 1747569300,
    }]
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": initial})
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    w.poll(top_addresses=["0xA"])  # in top 10
    api.set_activity("0xA", after)
    events = w.poll(top_addresses=[])  # dropped from top 10
    assert events == []  # CLOSE suppressed


def test_redeem_and_reward_events_skipped():
    """REDEEM/MERGE/REWARD should NOT generate watcher events."""
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": []})
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    w.poll(top_addresses=["0xA"])
    api.set_activity("0xA", [
        {"conditionId": "mX", "type": "REDEEM", "side": "", "outcome": "",
         "size": 100, "usdcSize": 100, "price": 0, "timestamp": 1747569100},
        {"conditionId": "mY", "type": "REWARD", "side": "", "outcome": "",
         "size": 50, "usdcSize": 5, "price": 0, "timestamp": 1747569200},
    ])
    events = w.poll(top_addresses=["0xA"])
    assert events == []
