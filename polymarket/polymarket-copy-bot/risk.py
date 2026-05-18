"""Daily loss circuit breaker.

Blocks NEW opens once today's realized PnL <= -DAILY_LOSS_LIMIT.
ALWAYS allows closes — so existing positions can still be unwound to
reduce exposure once the limit is hit (spec §3 last row).
"""
from clock import Clock
from storage import Storage


class RiskGate:
    def __init__(self, storage: Storage, clock: Clock,
                 daily_loss_limit: float):
        self.storage = storage
        self.clock = clock
        self.limit = daily_loss_limit

    def _today(self) -> str:
        return self.clock.now().date().isoformat()

    def allow_open(self) -> bool:
        pnl = self.storage.get_daily_pnl(self._today())
        if pnl <= -self.limit:
            if not self.storage.is_halted(self._today()):
                self.storage.mark_halted(self._today(),
                                         self.clock.now().isoformat())
            return False
        return True

    def allow_close(self) -> bool:
        return True

    def record_realized_pnl(self, delta: float) -> None:
        self.storage.add_daily_pnl(self._today(), delta)
