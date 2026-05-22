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
    # CRITICAL for LIVE: token_id must flow through to the Event so
    # LiveExecutor can place a CLOB order with the correct per-outcome ID.
    assert e.token_id == "asset_m9_yes"


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


def test_reward_events_skipped():
    """REWARD must not generate any event."""
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": []})
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    w.poll(top_addresses=["0xA"])
    api.set_activity("0xA", [
        {"conditionId": "mY", "type": "REWARD", "side": "", "outcome": "",
         "size": 50, "usdcSize": 5, "price": 0, "timestamp": 1747569200},
    ])
    events = w.poll(top_addresses=["0xA"])
    assert events == []


def test_redeem_emits_resolve_event():
    """REDEEM by source -> watcher emits RESOLVE so executor can mark
    matching positions as RESOLVED."""
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": []})
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    w.poll(top_addresses=["0xA"])  # baseline
    api.set_activity("0xA", [
        {"conditionId": "mX", "type": "REDEEM", "side": "", "outcome": "",
         "size": 100, "usdcSize": 100, "price": 0, "timestamp": 1747569100},
    ])
    events = w.poll(top_addresses=["0xA"])
    assert len(events) == 1
    assert events[0].kind == "RESOLVE"
    assert events[0].source_trader == "0xA"
    assert events[0].market_id == "mX"


def test_resolve_emitted_even_after_drop_from_top10():
    """RESOLVE is bookkeeping; it should fire regardless of E1 (unlike CLOSE)
    because we MUST free our G4 slot when the market actually resolved."""
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": []})
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    w.poll(top_addresses=["0xA"])
    api.set_activity("0xA", [
        {"conditionId": "mX", "type": "REDEEM", "side": "", "outcome": "",
         "size": 100, "usdcSize": 100, "price": 0, "timestamp": 1747569100},
    ])
    events = w.poll(top_addresses=[])  # dropped from top 10
    assert len(events) == 1
    assert events[0].kind == "RESOLVE"
