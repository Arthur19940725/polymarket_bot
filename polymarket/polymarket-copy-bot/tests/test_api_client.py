"""Tests for API client (FakeAPI used throughout)."""
import json
import os
from api_client import FakeAPI, Trade


def _load(fixtures_dir, name):
    with open(os.path.join(fixtures_dir, name)) as f:
        return json.load(f)


def test_fake_api_leaderboard(fixtures_dir):
    api = FakeAPI(
        leaderboard=_load(fixtures_dir, "leaderboard.json"),
        activity_by_addr={},
    )
    lb = api.leaderboard(limit=2)
    assert len(lb) == 2
    assert lb[0].address == "0xAlice"
    assert lb[0].pnl == 8000
    assert lb[0].pseudonym == "alice"


def test_fake_api_activity(fixtures_dir):
    api = FakeAPI(
        leaderboard=[],
        activity_by_addr={
            "0xAlice": _load(fixtures_dir, "activity_alice.json"),
        },
    )
    trades = api.user_activity("0xAlice", limit=10)
    assert len(trades) == 6
    assert isinstance(trades[0], Trade)
    assert trades[0].market_id == "m1"
    assert trades[0].event_type == "TRADE"
    assert trades[0].action == "BUY"
    assert trades[0].outcome == "Yes"
    # The REDEEM event is the last one
    assert trades[-1].event_type == "REDEEM"


def test_fake_api_activity_pagination(fixtures_dir):
    api = FakeAPI(
        leaderboard=[],
        activity_by_addr={
            "0xAlice": _load(fixtures_dir, "activity_alice.json"),
        },
    )
    page1 = api.user_activity("0xAlice", limit=2, offset=0)
    page2 = api.user_activity("0xAlice", limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].timestamp != page2[0].timestamp


def test_fake_api_activity_unknown_user_empty():
    api = FakeAPI(leaderboard=[], activity_by_addr={})
    assert api.user_activity("0xNobody") == []
