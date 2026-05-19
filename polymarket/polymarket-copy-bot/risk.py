"""Risk gate.

Three independent circuit breakers (all block NEW opens, always allow closes):

  1. Daily loss cap:  realized PnL today <= -daily_loss_limit  -> halt
  2. G3 global cap:   count(OPEN positions) >= max_open_positions  -> halt
  3. G4 per-trader:   count(OPEN per source) >= max_open_per_trader  -> halt

Closes always allowed so existing exposure can be unwound (spec §3 last row).
Any of max_open_positions / max_open_per_trader = None disables that check.
G4 requires the caller to pass source_trader; without it G4 is skipped.
"""
from typing import Optional
from clock import Clock
from storage import Storage


class RiskGate:
    def __init__(self, storage: Storage, clock: Clock,
                 daily_loss_limit: float,
                 max_open_positions: Optional[int] = None,
                 max_open_per_trader: Optional[int] = None):
        self.storage = storage
        self.clock = clock
        self.limit = daily_loss_limit
        self.max_open = max_open_positions
        self.max_per_trader = max_open_per_trader

    def _today(self) -> str:
        return self.clock.now().date().isoformat()

    def allow_open(self, source_trader: Optional[str] = None) -> bool:
        pnl = self.storage.get_daily_pnl(self._today())
        if pnl <= -self.limit:
            if not self.storage.is_halted(self._today()):
                self.storage.mark_halted(self._today(),
                                         self.clock.now().isoformat())
            return False
        open_positions = self.storage.list_open_positions()
        if self.max_open is not None:
            if len(open_positions) >= self.max_open:
                return False
        if self.max_per_trader is not None and source_trader is not None:
            same = sum(1 for p in open_positions
                       if p.source_trader == source_trader)
            if same >= self.max_per_trader:
                return False
        return True

    def allow_close(self) -> bool:
        return True

    def record_realized_pnl(self, delta: float) -> None:
        self.storage.add_daily_pnl(self._today(), delta)
