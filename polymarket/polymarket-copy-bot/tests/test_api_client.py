"""Tests for API client (focused on FakeAPI used throughout tests)."""
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


def test_fake_api_activity(fixtures_dir):
    api = FakeAPI(
        leaderboard=[],
        activity_by_addr={
            "0xAlice": _load(fixtures_dir, "activity_alice.json"),
        },
    )
    trades = api.user_activity("0xAlice")
    assert len(trades) == 3
    assert isinstance(trades[0], Trade)
    assert trades[0].market_id == "m1"
    assert trades[0].pnl_realized == 60
    assert trades[2].resolved is True


def test_fake_api_activity_unknown_user_empty():
    api = FakeAPI(leaderboard=[], activity_by_addr={})
    assert api.user_activity("0xNobody") == []
