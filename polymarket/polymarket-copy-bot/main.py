"""CLI entry point for the Polymarket copy-trading bot."""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone
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
                    daily_loss_limit=config.DAILY_LOSS_LIMIT)
    watcher = Watcher(api=api, clock=clock)

    if args.dry_run:
        executor = DryRunExecutor(
            storage=storage, api=api, clock=clock, gate=gate,
            copy_amount_usd=config.COPY_AMOUNT_USD,
            min_order_usd=config.MIN_ORDER_USD,
        )
        mode_str = "DRY-RUN"
    else:
        clob = _build_clob_client()
        executor = LiveExecutor(
            storage=storage, api=api, clock=clock, gate=gate,
            copy_amount_usd=config.COPY_AMOUNT_USD,
            min_order_usd=config.MIN_ORDER_USD,
            clob_client=clob,
        )
        mode_str = "LIVE"

    logging.info("Starting watcher in %s mode, poll=%ds, copy=$%.2f, "
                 "loss_limit=$%.2f",
                 mode_str, config.POLL_INTERVAL_SEC,
                 config.COPY_AMOUNT_USD, config.DAILY_LOSS_LIMIT)

    while True:
        today = clock.now().date().isoformat()
        top = storage.load_top_10(today)
        if not top:
            logging.warning("No top_10 for %s — run `main.py rank` first",
                            today)
            clock.sleep(config.POLL_INTERVAL_SEC)
            continue
        top_addrs = [t.trader_addr for t in top]
        try:
            events = watcher.poll(top_addrs)
        except Exception:
            logging.exception("poll failed; will retry")
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
