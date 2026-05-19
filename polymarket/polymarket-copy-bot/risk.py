"""Risk gate.

Two independent circuit breakers (both block NEW opens, always allow closes):

  1. Daily loss cap:  realized PnL today <= -daily_loss_limit  -> halt
  2. G3 position cap: count(OPEN positions) >= max_open_positions  -> halt

Closes always allowed so existing exposure can be unwound (spec §3 last row).
max_open_positions=None disables G3 (back-compat with original spec).
"""
from typing import Optional
from clock import Clock
from storage import Storage


class RiskGate:
    def __init__(self, storage: Storage, clock: Clock,
                 daily_loss_limit: float,
                 max_open_positions: Optional[int] = None):
        self.storage = storage
        self.clock = clock
        self.limit = daily_loss_limit
        self.max_open = max_open_positions

    def _today(self) -> str:
        return self.clock.now().date().isoformat()

    def allow_open(self) -> bool:
        pnl = self.storage.get_daily_pnl(self._today())
        if pnl <= -self.limit:
            if not self.storage.is_halted(self._today()):
                self.storage.mark_halted(self._today(),
                                         self.clock.now().isoformat())
            return False
        if self.max_open is not None:
            if len(self.storage.list_open_positions()) >= self.max_open:
                return False
        return True

    def allow_close(self) -> bool:
        return True

    def record_realized_pnl(self, delta: float) -> None:
        self.storage.add_daily_pnl(self._today(), delta)
