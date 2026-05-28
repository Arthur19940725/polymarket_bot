"""Activity-diffing watcher.

Each call to `poll()`:
  1. Fetches current activity for each top-10 address
  2. Diffs against the address's previous activity (by trade fingerprint)
  3. Emits events for new activity:
       - TRADE/BUY  -> OPEN    (only if source still in top 10; spec §3 E1)
       - TRADE/SELL -> CLOSE   (only if source still in top 10; spec §3 E1)
       - REDEEM     -> RESOLVE (always; we MUST free the G4 slot when the
                                market actually resolved, even if source
                                dropped out of top 10)
       - MERGE / REWARD        -> skipped
"""
from dataclasses import dataclass
from api_client import PolymarketAPI, Trade
from clock import Clock


@dataclass(frozen=True)
class Event:
    kind: str           # 'OPEN' | 'CLOSE' | 'RESOLVE'
    source_trader: str
    market_id: str
    side: str           # outcome string for OPEN/CLOSE; '' for RESOLVE
    price: float        # 0.0 for RESOLVE
    timestamp: int
    token_id: str = ""  # CTF token_id (= /activity 'asset' field). Required
                        # for LIVE orders; empty/unused for RESOLVE.
    slug: str = ""      # market slug for human signals; URL = /event/<slug>
    title: str = ""     # human-readable market title


def _fingerprint(t: Trade) -> tuple:
    return (t.market_id, t.outcome, t.event_type, t.action,
            t.size, t.price, t.timestamp)


class Watcher:
    def __init__(self, api: PolymarketAPI, clock: Clock,
                 min_odds: float = 0.0, max_odds: float = 1.0):
        self.api = api
        self.clock = clock
        # OPEN events outside [min_odds, max_odds] are dropped. Extreme prices
        # (e.g. $0.999 near-certain markets) yield sub-cent returns on a $1
        # copy -- not worth the gas/slippage. CLOSE/RESOLVE ignore this.
        self.min_odds = min_odds
        self.max_odds = max_odds
        # address -> set of trade fingerprints seen
        self._seen: dict[str, set[tuple]] = {}

    def poll(self, top_addresses: list[str]) -> list[Event]:
        top_set = set(top_addresses)
        addresses_to_poll = top_set | set(self._seen.keys())
        events: list[Event] = []
        for addr in addresses_to_poll:
            current = self.api.user_activity(addr)
            current_fps = {_fingerprint(t) for t in current}
            previous_fps = self._seen.get(addr)
            if previous_fps is None:
                self._seen[addr] = current_fps
                continue
            new_fps = current_fps - previous_fps
            for t in current:
                if _fingerprint(t) not in new_fps:
                    continue
                if t.event_type == "REDEEM":
                    # RESOLVE always fires (bookkeeping), even if dropped from top 10
                    events.append(Event(
                        kind="RESOLVE", source_trader=addr,
                        market_id=t.market_id, side="",
                        price=0.0, timestamp=t.timestamp,
                    ))
                    continue
                if t.event_type != "TRADE":
                    continue  # skip MERGE / REWARD
                if addr not in top_set:
                    continue  # E1 rule
                if t.action == "BUY":
                    if not (self.min_odds <= t.price <= self.max_odds):
                        continue  # skip extreme-odds opens
                    events.append(Event(
                        kind="OPEN", source_trader=addr,
                        market_id=t.market_id, side=t.outcome,
                        price=t.price, timestamp=t.timestamp,
                        token_id=t.token_id,
                        slug=t.slug, title=t.title,
                    ))
                elif t.action == "SELL":
                    events.append(Event(
                        kind="CLOSE", source_trader=addr,
                        market_id=t.market_id, side=t.outcome,
                        price=t.price, timestamp=t.timestamp,
                        token_id=t.token_id,
                        slug=t.slug, title=t.title,
                    ))
            self._seen[addr] = current_fps
        return events
