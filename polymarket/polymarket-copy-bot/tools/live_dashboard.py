"""Live terminal dashboard for the running watcher.

Tails the watcher log + reads the SQLite state and prints a compact
status panel that auto-refreshes. Read-only -- safe to run alongside
the watcher (SQLite WAL handles concurrent reads).

Usage:
    python tools/live_dashboard.py
    python tools/live_dashboard.py --log /tmp/watch_v5.log --interval 10

Press Ctrl-C to exit.
"""
import argparse
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Regex to pick up the meaningful lines without parsing every entry.
_OPEN_RE = re.compile(r"\[dry-run OPEN\] (\S+) (\S+) (.+?) @ ([\d.]+)")
_CLOSE_RE = re.compile(r"\[dry-run CLOSE\] .* \(pnl=\$(-?[\d.]+)")
_RESOLVE_RE = re.compile(
    r"\[dry-run RESOLVE\] \S+ \S+ .* \(pnl=\$(-?[\d.]+), (win|LOSS|assumed)")
_BLOCK_RE = re.compile(r"\[risk\] open blocked")
_LIVE_OPEN_RE = re.compile(r"\[LIVE OPEN\]")
_FAIL_RE = re.compile(r"poll failed.*consecutive=(\d+)")
_EVENT_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def compute_state(log_path: str, db_path: str,
                  today: str | None = None) -> dict:
    """Read recent watcher state. Returns a dict that render() consumes."""
    if today is None:
        today = datetime.now(timezone.utc).date().isoformat()
    counts = {"open": 0, "close": 0,
              "resolve_win": 0, "resolve_loss": 0,
              "resolve_assumed": 0, "blocks": 0, "live_open": 0,
              "max_fail_streak": 0}
    last_events: list[str] = []
    path = Path(log_path)
    if path.exists():
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if _OPEN_RE.search(line):
                    counts["open"] += 1
                    last_events.append(_short_event(line, "OPEN"))
                elif _CLOSE_RE.search(line):
                    counts["close"] += 1
                    last_events.append(_short_event(line, "CLOSE"))
                elif _RESOLVE_RE.search(line):
                    m = _RESOLVE_RE.search(line)
                    kind = m.group(2)
                    if kind == "win":
                        counts["resolve_win"] += 1
                    elif kind == "LOSS":
                        counts["resolve_loss"] += 1
                    else:
                        counts["resolve_assumed"] += 1
                    last_events.append(_short_event(line, "RESOLVE"))
                elif _LIVE_OPEN_RE.search(line):
                    counts["live_open"] += 1
                    last_events.append(_short_event(line, "LIVE_OPEN"))
                elif _BLOCK_RE.search(line):
                    counts["blocks"] += 1
                fm = _FAIL_RE.search(line)
                if fm:
                    n = int(fm.group(1))
                    if n > counts["max_fail_streak"]:
                        counts["max_fail_streak"] = n

    open_by_trader: list[tuple[str, int]] = []
    pnl_today = 0.0
    open_total = 0
    if Path(db_path).exists():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT source_trader, COUNT(*) as c FROM our_positions "
            "WHERE status='OPEN' GROUP BY source_trader "
            "ORDER BY c DESC, source_trader ASC"
        ).fetchall()
        open_by_trader = [(r["source_trader"], r["c"]) for r in rows]
        open_total = sum(c for _, c in open_by_trader)
        pnl = conn.execute(
            "SELECT COALESCE(SUM(realized_pnl), 0) as p FROM our_positions "
            "WHERE status IN ('RESOLVED', 'MIRRORED_CLOSE') "
            "AND substr(closed_at, 1, 10) = ?", (today,)
        ).fetchone()
        pnl_today = float(pnl["p"]) if pnl else 0.0
        conn.close()

    return {
        "counts": counts,
        "last_events": last_events[-5:],
        "open_by_trader": open_by_trader,
        "open_total": open_total,
        "pnl_today": round(pnl_today, 2),
        "today": today,
    }


def _short_event(line: str, kind: str) -> str:
    """Trim a verbose log line into ~80-char dashboard form."""
    m = _EVENT_TS_RE.match(line)
    ts = m.group(1)[11:19] if m else "?"
    rest = line.split("INFO executor: ", 1)[-1].strip()
    if len(rest) > 100:
        rest = rest[:97] + "..."
    return f"{ts}  {rest}"


def render(state: dict) -> str:
    c = state["counts"]
    bar = "=" * 72
    lines = [
        bar,
        f"Polymarket Copy-Bot  --  Live Dashboard  --  {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        bar,
        f"OPEN={c['open']:>3}  CLOSE={c['close']:>3}  "
        f"RESOLVE win={c['resolve_win']:>3}/LOSS={c['resolve_loss']:>3}/"
        f"assumed={c['resolve_assumed']:>3}  "
        f"blocks={c['blocks']:>6}  "
        f"LIVE_OPEN={c['live_open']}",
        f"Max consecutive poll failures: {c['max_fail_streak']}",
        "",
        f"DB:  {state['open_total']} OPEN positions "
        f"|  Today ({state['today']}) realized PnL: "
        f"${state['pnl_today']:+.2f}",
    ]
    if state["open_by_trader"]:
        lines.append("Per-trader OPEN:")
        for addr, n in state["open_by_trader"][:6]:
            lines.append(f"  {addr[:14]}... -> {n}")
    lines.append("")
    lines.append("Last 5 events:")
    if state["last_events"]:
        for ev in state["last_events"]:
            lines.append(f"  {ev}")
    else:
        lines.append("  (none yet)")
    lines.append(bar)
    return "\n".join(lines)


def _clear_screen() -> None:
    # ANSI clear works on modern Windows 10+ terminals and all POSIX.
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default="/tmp/watch_v5.log",
                        help="watcher log path")
    parser.add_argument("--db", default="data/bot.sqlite",
                        help="SQLite path")
    parser.add_argument("--interval", type=int, default=10,
                        help="refresh interval seconds")
    parser.add_argument("--once", action="store_true",
                        help="render once and exit (good for cron)")
    args = parser.parse_args(argv)
    while True:
        state = compute_state(log_path=args.log, db_path=args.db)
        if not args.once:
            _clear_screen()
        print(render(state))
        if args.once:
            return 0
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nbye")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
