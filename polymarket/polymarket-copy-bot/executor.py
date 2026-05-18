"""Executor: handles OPEN/CLOSE events.

DryRunExecutor: logs to storage with dry_run=True, never calls CLOB.
LiveExecutor:   places real orders via py-clob-client.

Both share the same interface (handle_event) so the watcher loop is
mode-agnostic.
"""
import logging
from typing import Optional
from api_client import PolymarketAPI
from clock import Clock
from storage import Storage, Position, TradeRow
from risk import RiskGate
from watcher import Event

logger = logging.getLogger(__name__)


class DryRunExecutor:
    """Simulates order execution. No network calls except price lookup."""

    def __init__(self, storage: Storage, api: PolymarketAPI, clock: Clock,
                 gate: RiskGate, copy_amount_usd: float,
                 min_order_usd: float = 1.0):
        self.storage = storage
        self.api = api
        self.clock = clock
        self.gate = gate
        self.copy_amount_usd = copy_amount_usd
        self.min_order_usd = min_order_usd

    def _now(self) -> str:
        return self.clock.now().isoformat()

    def handle_event(self, event: Event) -> None:
        if event.kind == "OPEN":
            self._handle_open(event)
        elif event.kind == "CLOSE":
            self._handle_close(event)

    def _handle_open(self, e: Event) -> None:
        if not self.gate.allow_open():
            logger.info("[risk] open blocked: %s %s %s",
                        e.source_trader, e.market_id, e.side)
            return
        existing = self.storage.get_open_position(
            e.source_trader, e.market_id, e.side)
        if existing is not None:
            logger.info("[skip] already holding %s/%s/%s",
                        e.source_trader, e.market_id, e.side)
            return
        size_usd = max(self.copy_amount_usd, self.min_order_usd)
        shares = size_usd / e.price if e.price > 0 else 0
        pid = self.storage.insert_position(Position(
            source_trader=e.source_trader, market_id=e.market_id,
            side=e.side, size_usd=size_usd, opened_at=self._now(),
            status="OPEN",
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
        if not self.gate.allow_open():
            return
        existing = self.storage.get_open_position(
            e.source_trader, e.market_id, e.side)
        if existing is not None:
            return
        size_usd = max(self.copy_amount_usd, self.min_order_usd)
        shares = size_usd / e.price if e.price > 0 else 0
        try:
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY
            order = self.clob.create_and_post_order(OrderArgs(
                token_id=e.market_id,
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
        try:
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import SELL
            order = self.clob.create_and_post_order(OrderArgs(
                token_id=e.market_id, price=round(e.price, 2),
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
