"""Tests for tools/live_dashboard.py."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from storage import Storage, Position, TopTrader
import live_dashboard as ld


def _write_log(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def test_compute_state_counts_events(tmp_path, tmp_db_path):
    Storage(tmp_db_path)
    log = tmp_path / "watch.log"
    _write_log(log, [
        "2026-05-26 18:09:19,530 INFO executor: [dry-run OPEN] 0xA m1 Yes @ 0.4000 (size=$1.00)",
        "2026-05-26 18:09:53,056 INFO executor: [dry-run OPEN] 0xA m2 No @ 0.5000 (size=$1.00)",
        "2026-05-26 18:10:00,000 INFO executor: [risk] open blocked: 0xA m3 Yes",
        "2026-05-26 18:10:00,001 INFO executor: [risk] open blocked: 0xA m3 Yes",
        "2026-05-26 18:11:00,000 INFO executor: [dry-run RESOLVE] 0xA m1 Yes (pnl=$0.60, win)",
        "2026-05-26 18:11:30,000 INFO executor: [dry-run RESOLVE] 0xA m2 No (pnl=$-0.50, LOSS)",
    ])
    state = ld.compute_state(log_path=str(log), db_path=tmp_db_path)
    assert state["counts"]["open"] == 2
    assert state["counts"]["resolve_win"] == 1
    assert state["counts"]["resolve_loss"] == 1
    assert state["counts"]["blocks"] == 2


def test_compute_state_per_trader_open_breakdown(tmp_path, tmp_db_path):
    s = Storage(tmp_db_path)
    s.insert_position(Position(
        source_trader="0xA", market_id="m1", side="Yes",
        size_usd=1.0, opened_at="2026-05-26T00:00:00+00:00",
        status="OPEN", token_id="tok1"))
    s.insert_position(Position(
        source_trader="0xA", market_id="m2", side="No",
        size_usd=1.0, opened_at="2026-05-26T00:00:00+00:00",
        status="OPEN", token_id="tok2"))
    s.insert_position(Position(
        source_trader="0xB", market_id="m3", side="Yes",
        size_usd=1.0, opened_at="2026-05-26T00:00:00+00:00",
        status="OPEN", token_id="tok3"))
    log = tmp_path / "watch.log"
    _write_log(log, [])
    state = ld.compute_state(log_path=str(log), db_path=tmp_db_path)
    assert state["open_by_trader"][:2] == [("0xA", 2), ("0xB", 1)]


def test_compute_state_pnl_today_only(tmp_db_path, tmp_path):
    s = Storage(tmp_db_path)
    # Resolved today: +0.60 and -0.50 -> total +0.10
    pid = s.insert_position(Position(
        source_trader="0xA", market_id="m1", side="Yes",
        size_usd=1.0, opened_at="2026-05-25T20:00:00+00:00",
        status="OPEN", token_id="tok1"))
    s.close_position(pid, closed_at="2026-05-26T18:00:00+00:00",
                     realized_pnl=0.60, new_status="RESOLVED")
    pid2 = s.insert_position(Position(
        source_trader="0xA", market_id="m2", side="No",
        size_usd=1.0, opened_at="2026-05-25T20:00:00+00:00",
        status="OPEN", token_id="tok2"))
    s.close_position(pid2, closed_at="2026-05-26T19:00:00+00:00",
                     realized_pnl=-0.50, new_status="RESOLVED")
    # Resolved yesterday - must not be included in today
    pid3 = s.insert_position(Position(
        source_trader="0xB", market_id="m3", side="Yes",
        size_usd=1.0, opened_at="2026-05-24T00:00:00+00:00",
        status="OPEN", token_id="tok3"))
    s.close_position(pid3, closed_at="2026-05-25T10:00:00+00:00",
                     realized_pnl=99.99, new_status="RESOLVED")
    log = tmp_path / "watch.log"
    _write_log(log, [])
    state = ld.compute_state(log_path=str(log), db_path=tmp_db_path,
                             today="2026-05-26")
    assert state["pnl_today"] == 0.10


def test_render_contains_key_sections(tmp_db_path, tmp_path):
    Storage(tmp_db_path)
    log = tmp_path / "watch.log"
    _write_log(log, [])
    state = ld.compute_state(log_path=str(log), db_path=tmp_db_path)
    text = ld.render(state)
    assert "OPEN" in text
    assert "RESOLVE" in text
    assert "blocks" in text.lower()


def test_render_truncates_last_events_to_5(tmp_db_path, tmp_path):
    Storage(tmp_db_path)
    log = tmp_path / "watch.log"
    lines = [f"2026-05-26 18:0{i}:00,000 INFO executor: [dry-run OPEN] 0xA m{i} Yes @ 0.4 (size=$1.00)"
             for i in range(9)]
    _write_log(log, lines)
    state = ld.compute_state(log_path=str(log), db_path=tmp_db_path)
    # Only last 5 should be in state['last_events']
    assert len(state["last_events"]) == 5
