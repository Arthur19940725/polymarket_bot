"""Compare top_10 rankings between two UTC dates.

Usage:
    python tools/compare_days.py 2026-05-19 2026-05-20

Shows: who moved up/down/in/out, and per-trader metric deltas.
Reads from data/bot.sqlite (the bot's state store).
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def _load_top(conn, date: str) -> list[dict]:
    rows = conn.execute(
        "SELECT rank, trader_addr, score, win_rate, total_pnl, sharpe_like "
        "FROM top_10 WHERE date = ? ORDER BY rank",
        (date,),
    ).fetchall()
    return [dict(r) for r in rows]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("date_a", help="earlier UTC date, e.g. 2026-05-19")
    p.add_argument("date_b", help="later UTC date,   e.g. 2026-05-20")
    p.add_argument("--db", default="data/bot.sqlite",
                   help="path to bot.sqlite (default: data/bot.sqlite)")
    args = p.parse_args(argv)

    if not Path(args.db).exists():
        print(f"ERROR: {args.db} not found", file=sys.stderr)
        return 2

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    a = _load_top(conn, args.date_a)
    b = _load_top(conn, args.date_b)

    if not a:
        print(f"No top_10 for {args.date_a}", file=sys.stderr)
        return 2
    if not b:
        print(f"No top_10 for {args.date_b}", file=sys.stderr)
        return 2

    a_by_addr = {r["trader_addr"]: r for r in a}
    b_by_addr = {r["trader_addr"]: r for r in b}
    all_addrs = set(a_by_addr) | set(b_by_addr)

    print(f"\n=== Top-N comparison: {args.date_a}  ->  {args.date_b} ===\n")
    print(f"  {args.date_a}: {len(a)} traders")
    print(f"  {args.date_b}: {len(b)} traders\n")

    print(f"{'Addr':<14}{'A rank':>8}{'B rank':>8}{'Δscore':>10}"
          f"{'Δwin%':>9}{'ΔPnL':>14}{'status':>12}")
    print("-" * 80)

    rows = []
    for addr in all_addrs:
        ra, rb = a_by_addr.get(addr), b_by_addr.get(addr)
        if ra and rb:
            status = "stayed"
            if rb["rank"] < ra["rank"]:
                status = "up"
            elif rb["rank"] > ra["rank"]:
                status = "down"
            d_score = rb["score"] - ra["score"]
            d_win = (rb["win_rate"] - ra["win_rate"]) * 100
            d_pnl = rb["total_pnl"] - ra["total_pnl"]
            sort_key = rb["rank"]
        elif rb:
            status = "NEW"
            d_score = d_win = d_pnl = float("nan")
            sort_key = rb["rank"]
        else:
            status = "DROPPED"
            d_score = d_win = d_pnl = float("nan")
            sort_key = 99
        rows.append((sort_key, addr, ra, rb, d_score, d_win, d_pnl, status))

    rows.sort(key=lambda x: x[0])
    for _, addr, ra, rb, ds, dw, dp, status in rows:
        a_rank = f"{ra['rank']}" if ra else "-"
        b_rank = f"{rb['rank']}" if rb else "-"
        ds_s = f"{ds:+.3f}" if ds == ds else "n/a"
        dw_s = f"{dw:+.2f}" if dw == dw else "n/a"
        dp_s = f"{dp:+.2f}" if dp == dp else "n/a"
        print(f"{addr[:12] + '..':<14}{a_rank:>8}{b_rank:>8}"
              f"{ds_s:>10}{dw_s:>9}{dp_s:>14}{status:>12}")

    # Positions resolved overnight (REDEEM impact)
    print()
    n_redeemed = conn.execute(
        "SELECT COUNT(*) FROM our_positions "
        "WHERE status='RESOLVED' OR status='MIRRORED_CLOSE'"
    ).fetchone()[0]
    n_open = conn.execute(
        "SELECT COUNT(*) FROM our_positions WHERE status='OPEN'"
    ).fetchone()[0]
    print(f"Positions:  open={n_open}  resolved/closed={n_redeemed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
