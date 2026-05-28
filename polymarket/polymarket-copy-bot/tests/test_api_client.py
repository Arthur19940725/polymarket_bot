"""Tests for API client (FakeAPI used throughout)."""
import json
import os
import requests
from api_client import FakeAPI, Trade, RequestsPolymarketAPI


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


def test_trade_carries_token_id_from_asset_field():
    """LIVE bug: CLOB orders need per-outcome token_id, not conditionId.
    The /activity event has it in the 'asset' field - we must keep it."""
    api = FakeAPI(
        leaderboard=[],
        activity_by_addr={"0xA": [
            {"conditionId": "0xMARKET", "asset": "1021106301963985907339",
             "type": "TRADE", "side": "BUY", "outcome": "Yes",
             "size": 100, "usdcSize": 40, "price": 0.4, "timestamp": 1},
        ]},
    )
    trades = api.user_activity("0xA")
    assert trades[0].token_id == "1021106301963985907339"


def test_trade_token_id_defaults_empty_when_missing():
    """REDEEM events sometimes have asset='' - shouldn't crash."""
    api = FakeAPI(
        leaderboard=[],
        activity_by_addr={"0xA": [
            {"conditionId": "0xMARKET", "type": "REDEEM",
             "side": "", "outcome": "", "size": 100, "usdcSize": 100,
             "price": 0, "timestamp": 1},
        ]},
    )
    trades = api.user_activity("0xA")
    assert trades[0].token_id == ""


def test_trade_carries_slug_and_title_for_signal_output():
    """Signal output needs slug (-> URL) + title (human label)."""
    api = FakeAPI(
        leaderboard=[],
        activity_by_addr={"0xA": [
            {"conditionId": "0xM", "asset": "asset_x",
             "type": "TRADE", "side": "BUY", "outcome": "Yes",
             "size": 100, "usdcSize": 40, "price": 0.4, "timestamp": 1,
             "slug": "test-event-2026", "title": "Test Event"},
        ]},
    )
    t = api.user_activity("0xA")[0]
    assert t.slug == "test-event-2026"
    assert t.title == "Test Event"


def test_connection_error_rebuilds_session(monkeypatch):
    """issue #12: a ConnectionError must trigger a fresh session so the
    next retry doesn't reuse a dead connection pool."""
    api = RequestsPolymarketAPI()
    first_session = api._session
    calls = {"n": 0}

    def boom(*a, **kw):
        calls["n"] += 1
        raise requests.exceptions.ConnectionError("dead socket")

    # Patch the session's get to always fail with ConnectionError.
    monkeypatch.setattr(first_session, "get", boom)

    # _get retries 3x via tenacity; after it gives up, the session must
    # have been replaced with a new object.
    import pytest
    from tenacity import RetryError
    with pytest.raises(RetryError):
        api._get("https://example.com/x")

    assert api._session is not first_session, "session should be rebuilt"
    assert calls["n"] >= 1


def test_build_session_sets_browser_ua():
    s = RequestsPolymarketAPI._build_session()
    assert "Mozilla" in s.headers["User-Agent"]
    assert s.headers["Accept"] == "application/json"
