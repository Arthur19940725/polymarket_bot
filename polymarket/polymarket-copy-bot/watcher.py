"""Activity-diffing watcher.

Each call to `poll()`:
  1. Fetches current activity for each top-10 address
  2. Diffs against the address's previous activity (by trade fingerprint)
  3. Emits OPEN/CLOSE events for new trades
  4. Suppresses CLOSE events for addresses no longer in top 10 (spec §3 E1)
"""
from dataclasses import dataclass
from api_client import PolymarketAPI, Trade
from clock import Clock


@dataclass(frozen=True)
class Event:
    kind: str  # 'OPEN' | 'CLOSE'
    source_trader: str
    market_id: str
    side: str  # 'YES' | 'NO'
    price: float
    timestamp: int


def _fingerprint(t: Trade) -> tuple:
    return (t.market_id, t.side, t.type, t.size, t.price, t.timestamp)


class Watcher:
    def __init__(self, api: PolymarketAPI, clock: Clock):
        self.api = api
        self.clock = clock
        # address -> set of trade fingerprints seen
        self._seen: dict[str, set[tuple]] = {}

    def poll(self, top_addresses: list[str]) -> list[Event]:
        top_set = set(top_addresses)
        # Union of (current top 10) and (anyone we've ever seen) — we still
        # need to track previously-seen addresses to detect their dropouts,
        # but we only emit events conditioned on top_set membership below.
        addresses_to_poll = top_set | set(self._seen.keys())
        events: list[Event] = []
        for addr in addresses_to_poll:
            current = self.api.user_activity(addr)
            current_fps = {_fingerprint(t) for t in current}
            previous_fps = self._seen.get(addr)
            if previous_fps is None:
                # First time seeing this address; just baseline.
                self._seen[addr] = current_fps
                continue
            new_fps = current_fps - previous_fps
            for t in current:
                if _fingerprint(t) not in new_fps:
                    continue
                if t.type == "BUY":
                    if addr in top_set:
                        events.append(Event(
                            kind="OPEN", source_trader=addr,
                            market_id=t.market_id, side=t.side,
                            price=t.price, timestamp=t.timestamp,
                        ))
                elif t.type == "SELL":
                    if addr in top_set:
                        events.append(Event(
                            kind="CLOSE", source_trader=addr,
                            market_id=t.market_id, side=t.side,
                            price=t.price, timestamp=t.timestamp,
                        ))
            self._seen[addr] = current_fps
        return events
