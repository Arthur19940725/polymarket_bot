"""CLI entry point for the Polymarket copy-trading bot."""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional
from api_client import RequestsPolymarketAPI
from clock import RealClock
from storage import Storage
from ranker import Ranker
from watcher import Watcher
from risk import RiskGate
from executor import DryRunExecutor, LiveExecutor
import config


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _prevent_system_sleep() -> bool:
    """Ask the OS to stay awake while the watcher runs.

    Windows: SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED).
    Other OSes: no-op (caller can use caffeinate / systemd-inhibit manually).
    Returns True if the request was accepted, False otherwise.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        prev = ctypes.windll.kernel32.SetThreadExecutionState(flags)
        return prev != 0
    except Exception:
        logging.exception("SetThreadExecutionState failed")
        return False


def cmd_rank(args) -> int:
    storage = Storage(config.DB_PATH)
    api = RequestsPolymarketAPI()
    clock = RealClock()
    ranker = Ranker(api=api, clock=clock, storage=storage)
    top = ranker.rank_and_persist(n=10)
    print(f"\nTop {len(top)} traders for {clock.now().date()}:")
    print(f"{'Rank':<5} {'Address':<44} {'Score':>8} {'WinRate':>8} "
          f"{'PnL':>10} {'Sharpe':>8}")
    for t in top:
        print(f"{t.rank:<5} {t.trader_addr:<44} {t.score:>8.3f} "
              f"{t.win_rate:>8.2%} {t.total_pnl:>10.2f} {t.sharpe_like:>8.3f}")
    return 0


def cmd_watch(args) -> int:
    if not args.dry_run and not args.live:
        print("ERROR: must specify --dry-run or --live", file=sys.stderr)
        return 2
    if args.live and os.getenv("CONFIRM_LIVE") != "yes":
        print("ERROR: --live requires CONFIRM_LIVE=yes in environment "
              "to prevent accidental real trading.", file=sys.stderr)
        return 2

    storage = Storage(config.DB_PATH)
    api = RequestsPolymarketAPI()
    clock = RealClock()
    gate = RiskGate(storage=storage, clock=clock,
                    daily_loss_limit=config.DAILY_LOSS_LIMIT,
                    max_open_positions=config.MAX_OPEN_POSITIONS,
                    max_open_per_trader=config.MAX_OPEN_PER_TRADER)
    watcher = Watcher(api=api, clock=clock)

    if args.dry_run:
        executor = DryRunExecutor(
            storage=storage, api=api, clock=clock, gate=gate,
            copy_amount_usd=config.COPY_AMOUNT_USD,
            min_order_usd=config.MIN_ORDER_USD,
            signals_jsonl_path=config.SIGNALS_JSONL_PATH,
        )
        mode_str = "DRY-RUN"
    else:
        clob = _build_clob_client()
        executor = LiveExecutor(
            storage=storage, api=api, clock=clock, gate=gate,
            copy_amount_usd=config.COPY_AMOUNT_USD,
            min_order_usd=config.MIN_ORDER_USD,
            clob_client=clob,
            signals_jsonl_path=config.SIGNALS_JSONL_PATH,
        )
        mode_str = "LIVE"

    logging.info("Starting watcher in %s mode, poll=%ds, copy=$%.2f, "
                 "max_open=%s, max_per_trader=%s, loss_limit=$%.2f",
                 mode_str, config.POLL_INTERVAL_SEC,
                 config.COPY_AMOUNT_USD,
                 config.MAX_OPEN_POSITIONS,
                 config.MAX_OPEN_PER_TRADER,
                 config.DAILY_LOSS_LIMIT)
    if _prevent_system_sleep():
        logging.info("system sleep prevented (Windows ES_SYSTEM_REQUIRED)")

    consecutive_poll_failures = 0
    last_auto_rank_fail_day: Optional[str] = None
    while True:
        today = clock.now().date().isoformat()
        top = storage.load_top_10(today)
        if not top:
            # Day rollover (or first run): auto-trigger today's rank so the
            # watcher doesn't sit idle until a human runs `main.py rank`.
            # If rank just failed for this day, don't hammer the API every
            # 30s -- back off until tomorrow.
            if last_auto_rank_fail_day != today:
                logging.info("No top_10 for %s; auto-ranking now", today)
                try:
                    ranker = Ranker(api=api, clock=clock, storage=storage)
                    top = ranker.rank_and_persist(n=10)
                    logging.info("auto-rank produced %d traders", len(top))
                except Exception:
                    logging.exception("auto-rank failed; waiting until next day")
                    last_auto_rank_fail_day = today
                    clock.sleep(config.POLL_INTERVAL_SEC)
                    continue
            if not top:
                clock.sleep(config.POLL_INTERVAL_SEC)
                continue
        top_addrs = [t.trader_addr for t in top]
        try:
            events = watcher.poll(top_addrs)
            consecutive_poll_failures = 0
        except Exception:
            consecutive_poll_failures += 1
            # Loud alarm when failures accumulate -- almost always means
            # CF / rate limit / network outage worth a human glance.
            level = (logging.ERROR if consecutive_poll_failures >= 5
                     else logging.WARNING)
            logging.log(level, "poll failed (consecutive=%d); will retry",
                        consecutive_poll_failures, exc_info=True)
            clock.sleep(config.POLL_INTERVAL_SEC)
            continue
        for ev in events:
            executor.handle_event(ev)
        clock.sleep(config.POLL_INTERVAL_SEC)


def cmd_backtest(args) -> int:
    from backtest import run_backtest
    pnl, n_trades = run_backtest(days=args.days, db_path=":memory:")
    print(f"\nBacktest over {args.days} days:")
    print(f"  Trades: {n_trades}")
    print(f"  Realized PnL: ${pnl:.2f}")
    return 0


def _build_clob_client():
    from py_clob_client.client import ClobClient
    client = ClobClient(
        config.CLOB_API,
        key=config.PRIVATE_KEY,
        chain_id=config.CHAIN_ID,
        signature_type=config.SIGNATURE_TYPE,
        funder=config.FUNDER_ADDRESS,
    )
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)
    return client


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="copy-bot",
                                description="Polymarket copy-trading bot")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_rank = sub.add_parser("rank", help="compute and store today's top 10")
    p_rank.set_defaults(func=cmd_rank)

    p_watch = sub.add_parser("watch", help="run the live watcher loop")
    g = p_watch.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--live", action="store_true")
    p_watch.set_defaults(func=cmd_watch)

    p_bt = sub.add_parser("backtest", help="replay historical data")
    p_bt.add_argument("--days", type=int, default=30)
    p_bt.set_defaults(func=cmd_backtest)

    return p


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
