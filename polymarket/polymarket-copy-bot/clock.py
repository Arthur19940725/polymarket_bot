"""Clock abstraction so live and backtest share code paths."""
import time as _time
from datetime import datetime, timezone, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...
    def sleep(self, seconds: float) -> None: ...


class RealClock:
    """Wall-clock used in live mode."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def sleep(self, seconds: float) -> None:
        _time.sleep(seconds)


class FakeClock:
    """Virtual clock for backtest — sleep advances time instantly."""

    def __init__(self, start: datetime):
        if start.tzinfo is None:
            raise ValueError("FakeClock requires timezone-aware datetime")
        self._now = start

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)

    def advance_to(self, target: datetime) -> None:
        if target < self._now:
            raise ValueError("cannot advance clock backwards")
        self._now = target
