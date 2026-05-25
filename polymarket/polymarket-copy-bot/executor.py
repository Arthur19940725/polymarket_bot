"""Executor: handles OPEN/CLOSE events.

DryRunExecutor: logs to storage with dry_run=True, never calls CLOB.
LiveExecutor:   places real orders via py-clob-client.

Both share the same interface (handle_event) so the watcher loop is
mode-agnostic.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from api_client import PolymarketAPI
from clock import Clock
from storage import Storage, Position, TradeRow, TopTrader
from risk import RiskGate
from watcher import Event

logger = logging.getLogger(__name__)

_POLYMARKET_BASE = "https://polymarket.com/event/"
_SIGNAL_BAR = "=" * 60


def format_signal(event: Event, trader_meta: Optional[TopTrader],
                  copy_amount_usd: float) -> str:
    """Render a human-actionable signal block for stdout/logs.

    The operator reads this and decides whether to manually place the trade
    on polymarket.com (used in regions where the bot cannot execute LIVE)."""
    ts = datetime.fromtimestamp(event.timestamp, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC") if event.timestamp else "now"
    url = _POLYMARKET_BASE + event.slug if event.slug else "(no slug)"
    title = event.title or "(unknown market)"
    short = event.source_trader[:12] + "..."
    if trader_meta is not None:
        meta = (f"rank #{trader_meta.rank}  "
                f"win {trader_meta.win_rate * 100:.0f}%  "
                f"PnL ${trader_meta.total_pnl:,.0f}")
    else:
        meta = "(no rank meta)"
    shares = (copy_amount_usd / event.price) if event.price > 0 else 0
    action_word = "BUY" if event.kind == "OPEN" else "SELL"
    lines = [
        _SIGNAL_BAR,
        f">>> SIGNAL  {ts}",
        f"Trader  {short}  ({meta})",
        f"Market  {title}",
        f"URL     {url}",
        f"Action  {action_word}  {event.side}  @ ${event.price:.4f}",
        f"Size    ${copy_amount_usd:.2f}  ~  {shares:.2f} shares",
        _SIGNAL_BAR,
    ]
    return "\n".join(lines)


class DryRunExecutor:
    """Simulates order execution. No network calls except price lookup."""

    def __init__(self, storage: Storage, api: PolymarketAPI, clock: Clock,
                 gate: RiskGate, copy_amount_usd: float,
                 min_order_usd: float = 1.0,
                 signals_jsonl_path: Optional[str] = None):
        self.storage = storage
        self.api = api
        self.clock = clock
        self.gate = gate
        self.copy_amount_usd = copy_amount_usd
        self.min_order_usd = min_order_usd
        self.signals_jsonl_path = signals_jsonl_path

    def _append_signal_jsonl(self, e: Event,
                             trader_meta: Optional[TopTrader]) -> None:
        if not self.signals_jsonl_path:
            return
        import json
        url = _POLYMARKET_BASE + e.slug if e.slug else ""
        record = {
            "ts": self.clock.now().isoformat(),
            "event_ts": e.timestamp,
            "source_trader": e.source_trader,
            "rank": trader_meta.rank if trader_meta else None,
            "win_rate": trader_meta.win_rate if trader_meta else None,
            "total_pnl": trader_meta.total_pnl if trader_meta else None,
            "market_id": e.market_id,
            "title": e.title,
            "slug": e.slug,
            "url": url,
            "side": e.side,
            "price": e.price,
            "copy_amount_usd": self.copy_amount_usd,
        }
        with open(self.signals_jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _now(self) -> str:
        return self.clock.now().isoformat()

    def handle_event(self, event: Event) -> None:
        if event.kind == "OPEN":
            self._handle_open(event)
        elif event.kind == "CLOSE":
            self._handle_close(event)
        elif event.kind == "RESOLVE":
            self._handle_resolve(event)

    def _handle_open(self, e: Event) -> None:
        if not self.gate.allow_open(source_trader=e.source_trader):
            logger.info("[risk] open blocked: %s %s %s",
                        e.source_trader, e.market_id, e.side)
            return
        existing = self.storage.get_open_position(
            e.source_trader, e.market_id, e.side)
        if existing is not None:
            logger.info("[skip] already holding %s/%s/%s",
                        e.source_trader, e.market_id, e.side)
            return
        # Emit operator signal *before* writing storage. The signal is the
        # primary deliverable in regions where LIVE is geoblocked.
        date_str = self.clock.now().date().isoformat()
        top = {t.trader_addr: t for t in self.storage.load_top_10(date_str)}
        meta = top.get(e.source_trader)
        logger.info("\n%s",
                    format_signal(e, meta, self.copy_amount_usd))
        self._append_signal_jsonl(e, meta)

        size_usd = max(self.copy_amount_usd, self.min_order_usd)
        shares = size_usd / e.price if e.price > 0 else 0
        pid = self.storage.insert_position(Position(
            source_trader=e.source_trader, market_id=e.market_id,
            side=e.side, size_usd=size_usd, opened_at=self._now(),
            status="OPEN", token_id=e.token_id,
        ))
        self.storage.record_trade(TradeRow(
            position_id=pid, action="OPEN", price=e.price, size=shares,
            tx_hash=None, ts=self._now(), dry_run=True,
        ))
        logger.info("[dry-run OPEN] %s %s %s @ %.4f (size=$%.2f)",
                    e.source_trader, e.market_id, e.side, e.price, size_usd)

    def _handle_close(self, e: Event) -> None:
        if not self.gate.allow_close():
            return
        pos = self.storage.get_open_position(
            e.source_trader, e.market_id, e.side)
        if pos is None:
            return
        opens = [t for t in self.storage.list_trades_for_position(pos.id)
                 if t.action == "OPEN"]
        if not opens:
            return
        open_price = opens[0].price
        shares = pos.size_usd / open_price
        realized = (e.price - open_price) * shares
        self.storage.close_position(
            pid=pos.id, closed_at=self._now(),
            realized_pnl=realized, new_status="MIRRORED_CLOSE",
        )
        self.storage.record_trade(TradeRow(
            position_id=pos.id, action="CLOSE", price=e.price, size=shares,
            tx_hash=None, ts=self._now(), dry_run=True,
        ))
        self.gate.record_realized_pnl(realized)
        logger.info("[dry-run CLOSE] %s %s %s @ %.4f (pnl=$%.2f)",
                    e.source_trader, e.market_id, e.side, e.price, realized)

    def _handle_resolve(self, e: Event) -> None:
        """REDEEM by source -> mark our OPEN positions on this market as RESOLVED.

        Source REDEEMs exactly the winning side's token. We compare each of
        our positions' token_id against the REDEEM event's token_id:
          - same token_id  -> we mirrored the winner, PnL = (1.0 - open_price) * shares
          - different      -> source held the losing side too (hedge); our
                              position was the loser, PnL = -open_price * shares
        If the position has no recorded token_id (legacy or unknown), fall
        back to the old optimistic-win behavior and flag it in the log.
        """
        positions = self.storage.list_open_positions_for_market(
            e.source_trader, e.market_id)
        if not positions:
            return
        for pos in positions:
            opens = [t for t in self.storage.list_trades_for_position(pos.id)
                     if t.action == "OPEN"]
            if not opens:
                continue
            open_price = opens[0].price
            shares = pos.size_usd / open_price
            # Decide win vs loss by comparing tokens. Unknown -> optimistic.
            if pos.token_id and e.token_id:
                won = (pos.token_id == e.token_id)
                outcome_note = "win" if won else "LOSS"
                close_price = 1.0 if won else 0.0
            else:
                won = True
                outcome_note = "assumed win (no token_id)"
                close_price = 1.0
            realized = (close_price - open_price) * shares
            self.storage.close_position(
                pid=pos.id, closed_at=self._now(),
                realized_pnl=realized, new_status="RESOLVED",
            )
            self.storage.record_trade(TradeRow(
                position_id=pos.id, action="CLOSE",
                price=close_price, size=shares,
                tx_hash=None, ts=self._now(), dry_run=True,
            ))
            self.gate.record_realized_pnl(realized)
            logger.info("[dry-run RESOLVE] %s %s %s (pnl=$%.2f, %s)",
                        e.source_trader, e.market_id, pos.side,
                        realized, outcome_note)


class LiveExecutor(DryRunExecutor):
    """Live executor. Subclasses DryRunExecutor to reuse bookkeeping logic;
    overrides only the order-placement steps to call CLOB.

    The first version intentionally calls super() for state writes and adds
    real-order placement around them. Failures roll back the state insertion
    by closing the position immediately with realized_pnl=0 — keeping the
    invariant that storage reflects what really happened on-chain.
    """

    def __init__(self, *args, clob_client, **kwargs):
        super().__init__(*args, **kwargs)
        self.clob = clob_client

    def _handle_open(self, e: Event) -> None:
        if not self.gate.allow_open(source_trader=e.source_trader):
            return
        existing = self.storage.get_open_position(
            e.source_trader, e.market_id, e.side)
        if existing is not None:
            return
        if not e.token_id:
            logger.warning("live OPEN skipped: no token_id on event "
                           "(source=%s market=%s)", e.source_trader, e.market_id)
            return
        size_usd = max(self.copy_amount_usd, self.min_order_usd)
        shares = size_usd / e.price if e.price > 0 else 0
        try:
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY
            order = self.clob.create_and_post_order(OrderArgs(
                token_id=e.token_id,
                price=round(e.price, 2),
                size=round(shares, 2),
                side=BUY,
            ))
        except Exception as exc:
            logger.exception("live OPEN failed: %s", exc)
            return
        pid = self.storage.insert_position(Position(
            source_trader=e.source_trader, market_id=e.market_id,
            side=e.side, size_usd=size_usd, opened_at=self._now(),
            status="OPEN",
        ))
        self.storage.record_trade(TradeRow(
            position_id=pid, action="OPEN", price=e.price, size=shares,
            tx_hash=order.get("orderID"), ts=self._now(), dry_run=False,
        ))
        logger.info("[LIVE OPEN] %s %s %s @ %.4f order=%s",
                    e.source_trader, e.market_id, e.side, e.price,
                    order.get("orderID"))

    def _handle_close(self, e: Event) -> None:
        pos = self.storage.get_open_position(
            e.source_trader, e.market_id, e.side)
        if pos is None:
            return
        opens = [t for t in self.storage.list_trades_for_position(pos.id)
                 if t.action == "OPEN"]
        if not opens:
            return
        open_price = opens[0].price
        shares = pos.size_usd / open_price
        if not e.token_id:
            logger.warning("live CLOSE skipped: no token_id on event "
                           "(source=%s market=%s)", e.source_trader, e.market_id)
            return
        try:
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import SELL
            order = self.clob.create_and_post_order(OrderArgs(
                token_id=e.token_id, price=round(e.price, 2),
                size=round(shares, 2), side=SELL,
            ))
        except Exception as exc:
            logger.exception("live CLOSE failed: %s", exc)
            return
        realized = (e.price - open_price) * shares
        self.storage.close_position(
            pid=pos.id, closed_at=self._now(),
            realized_pnl=realized, new_status="MIRRORED_CLOSE",
        )
        self.storage.record_trade(TradeRow(
            position_id=pos.id, action="CLOSE", price=e.price, size=shares,
            tx_hash=order.get("orderID"), ts=self._now(), dry_run=False,
        ))
        self.gate.record_realized_pnl(realized)
        logger.info("[LIVE CLOSE] pnl=$%.2f order=%s",
                    realized, order.get("orderID"))
