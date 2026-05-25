"""Generate a daily Markdown report from signals.jsonl + bot.sqlite.

Usage:
    python tools/daily_report.py                # yesterday (UTC)
    python tools/daily_report.py 2026-05-23     # specific date
    python tools/daily_report.py 2026-05-23 -o /tmp/report.md

The report answers four operator questions:
  1. How many signals did the bot give and from whom?
  2. What's the realized P/L (signals that resolved that day)?
  3. How are the top_10 trader rankings evolving day-over-day?
  4. What's still OPEN that needs operator attention?

Designed to be cheap to rerun -- pure read from local files.
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running as `python tools/daily_report.py` from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from storage import Storage  # noqa: E402


def _load_signals_for_date(path: Path, date: str) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("ts", "")
            if ts.startswith(date):
                out.append(rec)
    return out


def _signals_section(signals: list[dict]) -> list[str]:
    if not signals:
        return ["## Signals", "", "0 signals.", ""]
    by_trader: dict[str, list[dict]] = defaultdict(list)
    for s in signals:
        by_trader[s.get("source_trader", "?")].append(s)
    lines = [f"## Signals ({len(signals)} signals from "
             f"{len(by_trader)} trader{'s' if len(by_trader) > 1 else ''})", ""]
    for addr, sigs in sorted(by_trader.items(),
                             key=lambda kv: -len(kv[1])):
        meta = sigs[0]
        rank = meta.get("rank")
        win = meta.get("win_rate")
        pnl = meta.get("total_pnl")
        win_pct = f"{win * 100:.0f}%" if win is not None else "?"
        pnl_str = f"${pnl:,.0f}" if pnl is not None else "?"
        lines.append(f"### {addr[:14]}... -- rank #{rank}, "
                     f"win {win_pct}, lifetime PnL {pnl_str} "
                     f"({len(sigs)} signal{'s' if len(sigs) > 1 else ''})")
        lines.append("")
        for s in sigs:
            ts_short = s.get("ts", "")[11:19]
            title = (s.get("title", "(unknown)"))[:70]
            url = s.get("url", "")
            side = s.get("side", "?")
            price = s.get("price", 0.0)
            lines.append(f"- `{ts_short}` **{side}** @ ${price:.4f} -- "
                         f"[{title}]({url})")
        lines.append("")
    return lines


def _realized_pnl_section(conn: sqlite3.Connection, date: str) -> list[str]:
    closed = conn.execute(
        "SELECT source_trader, market_id, side, realized_pnl, status "
        "FROM our_positions "
        "WHERE substr(closed_at, 1, 10) = ? "
        "AND realized_pnl IS NOT NULL",
        (date,),
    ).fetchall()
    open_today = conn.execute(
        "SELECT source_trader, market_id, side, opened_at, size_usd "
        "FROM our_positions WHERE status='OPEN' "
        "AND substr(opened_at, 1, 10) = ?",
        (date,),
    ).fetchall()
    pnl_total = sum(r["realized_pnl"] for r in closed)
    wins = sum(1 for r in closed if r["realized_pnl"] > 0)
    losses = sum(1 for r in closed if r["realized_pnl"] < 0)

    lines = [f"## Realized PnL", ""]
    lines.append(f"Total: **${pnl_total:.2f}** "
                 f"({len(closed)} resolved -- {wins} win / {losses} loss)")
    lines.append("")
    if closed:
        lines.append("| Trader | Market | Side | PnL |")
        lines.append("|---|---|---|---|")
        for r in sorted(closed, key=lambda x: -x["realized_pnl"]):
            lines.append(
                f"| `{r['source_trader'][:12]}...` "
                f"| `{r['market_id'][:14]}...` "
                f"| {r['side'][:20]} "
                f"| ${r['realized_pnl']:+.2f} |"
            )
        lines.append("")
    lines.append(f"**{len(open_today)} still open** "
                 f"(opened today, awaiting resolution).")
    lines.append("")
    return lines


def _rank_diff_section(s: Storage, date: str) -> list[str]:
    today = s.load_top_10(date)
    prev_date = (datetime.fromisoformat(date)
                 - timedelta(days=1)).date().isoformat()
    yesterday = s.load_top_10(prev_date)
    if not today and not yesterday:
        return ["## Rank diff", "", "No rank data.", ""]
    today_map = {t.trader_addr: t for t in today}
    yest_map = {t.trader_addr: t for t in yesterday}
    all_addrs = set(today_map) | set(yest_map)
    lines = [f"## Rank diff ({prev_date} -> {date})", "",
             "| Trader | Yesterday | Today | Status |",
             "|---|---|---|---|"]
    rows = []
    for addr in all_addrs:
        a = yest_map.get(addr)
        b = today_map.get(addr)
        if a and b:
            if b.rank < a.rank:
                status = "up"
            elif b.rank > a.rank:
                status = "down"
            else:
                status = "stayed"
            sort_key = b.rank
        elif b:
            status = "NEW"
            sort_key = b.rank
        else:
            status = "DROPPED"
            sort_key = 99
        rows.append((sort_key, addr, a, b, status))
    rows.sort(key=lambda x: x[0])
    for _, addr, a, b, status in rows:
        a_rank = f"#{a.rank}" if a else "-"
        b_rank = f"#{b.rank}" if b else "-"
        lines.append(f"| `{addr[:14]}...` | {a_rank} | {b_rank} | {status} |")
    lines.append("")
    return lines


def build_report(date: str, db_path: str, signals_path: str) -> str:
    s = Storage(db_path)
    conn = s._conn()
    signals = _load_signals_for_date(Path(signals_path), date)
    sections = [
        f"# Polymarket Copy-Bot Daily Report -- {date}",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
    ]
    sections += _signals_section(signals)
    sections += _realized_pnl_section(conn, date)
    sections += _rank_diff_section(s, date)
    return "\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date", nargs="?",
                        help="UTC date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--db", default="data/bot.sqlite")
    parser.add_argument("--signals", default="data/signals.jsonl")
    parser.add_argument("-o", "--output",
                        help="write report to file (default: stdout)")
    args = parser.parse_args(argv)
    date = args.date or (datetime.now(timezone.utc).date()
                         - timedelta(days=1)).isoformat()
    md = build_report(date=date, db_path=args.db, signals_path=args.signals)
    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"wrote {len(md)} bytes to {args.output}", file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
