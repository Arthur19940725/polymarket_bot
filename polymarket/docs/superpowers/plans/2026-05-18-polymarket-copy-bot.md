# Polymarket Copy-Trading Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python bot that ranks Polymarket traders daily by a composite score (win-rate + cumulative PnL + risk-adjusted ROI), then mirror-copies the top 10's opens and exits with a fixed dollar amount per trade, gated by a daily loss limit. DRY_RUN-first with a built-in backtest mode.

**Architecture:** Five components (Ranker, Watcher, RiskGate, Executor, Backtest) sharing a SQLite state store and a `clock` abstraction so live and backtest paths share identical code. Ranker runs once daily; Watcher polls every 30s; events flow Watcher → RiskGate → Executor.

**Tech Stack:** Python 3.11+, `py-clob-client`, `requests`, `python-dotenv`, `tenacity`, `pytest`, `pytest-mock`, SQLite (stdlib `sqlite3`).

**Spec:** `polymarket/docs/superpowers/specs/2026-05-18-polymarket-copy-bot-design.md`

**Working directory for all tasks:** `polymarket/polymarket-copy-bot/`

---

## File Structure

```
polymarket-copy-bot/
├── main.py              # CLI entry: rank / watch / backtest
├── config.py            # Env-loaded constants
├── clock.py             # Real + fake clock for backtest
├── storage.py           # SQLite wrapper (4 tables)
├── api_client.py        # Polymarket Data-API + CLOB wrappers
├── ranker.py            # Composite-score top-10 selection
├── watcher.py           # 30s polling, activity diff, emits events
├── risk.py              # Daily loss circuit breaker
├── executor.py          # Order placement (dry_run logs, live calls CLOB)
├── backtest.py          # Historical replay
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── conftest.py          # pytest shared fixtures
├── tests/
│   ├── __init__.py
│   ├── test_storage.py
│   ├── test_clock.py
│   ├── test_ranker.py
│   ├── test_watcher.py
│   ├── test_risk.py
│   ├── test_executor.py
│   ├── test_backtest.py
│   └── fixtures/
│       ├── leaderboard.json
│       ├── activity_alice.json
│       ├── activity_bob.json
│       └── activity_alice_t2.json   # alice's activity 30s later (with new trade)
└── data/
    └── .gitkeep         # bot.sqlite lives here, gitignored
```

All Python files capped at 300 lines per project rule.

---

## Task 1: Project Scaffold + Pytest Setup

**Files:**
- Create: `polymarket-copy-bot/requirements.txt`
- Create: `polymarket-copy-bot/.env.example`
- Create: `polymarket-copy-bot/.gitignore`
- Create: `polymarket-copy-bot/config.py`
- Create: `polymarket-copy-bot/conftest.py`
- Create: `polymarket-copy-bot/tests/__init__.py`
- Create: `polymarket-copy-bot/data/.gitkeep`

- [ ] **Step 1: Create directory structure**

```bash
cd polymarket
mkdir -p polymarket-copy-bot/tests/fixtures polymarket-copy-bot/data
touch polymarket-copy-bot/tests/__init__.py polymarket-copy-bot/data/.gitkeep
```

- [ ] **Step 2: Write `requirements.txt`**

```
py-clob-client>=0.18.0
requests>=2.31.0
python-dotenv>=1.0.0
tenacity>=8.2.0
web3==6.14.0
pytest>=8.0.0
pytest-mock>=3.12.0
```

- [ ] **Step 3: Write `.env.example`**

```
# Wallet (reuse from polymarket-arb-bot)
POLYMARKET_PRIVATE_KEY=
POLYMARKET_FUNDER_ADDRESS=
SIGNATURE_TYPE=1

# Copy strategy
COPY_AMOUNT_USD=5
DAILY_LOSS_LIMIT=50

# Ranker
RANK_WINDOW_DAYS=90
RANK_WEIGHTS=0.3,0.3,0.4
RANK_CANDIDATE_POOL_SIZE=500
MIN_RESOLVED_MARKETS=20
MIN_LIFETIME_VOLUME_USD=1000
MIN_LAST_TRADE_DAYS=14

# Watcher
POLL_INTERVAL_SEC=30

# Storage
DB_PATH=data/bot.sqlite
```

- [ ] **Step 4: Write `.gitignore`**

```
.env
data/*.sqlite
data/*.sqlite-journal
__pycache__/
*.pyc
.pytest_cache/
.venv/
```

- [ ] **Step 5: Write `config.py`**

```python
"""Polymarket copy-trading bot configuration."""
import os
from dotenv import load_dotenv

load_dotenv()

# API endpoints
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

# Chain
CHAIN_ID = 137

# Wallet
PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")
FUNDER_ADDRESS = os.getenv("POLYMARKET_FUNDER_ADDRESS", "")
SIGNATURE_TYPE = int(os.getenv("SIGNATURE_TYPE", "1"))

# Copy strategy
COPY_AMOUNT_USD = float(os.getenv("COPY_AMOUNT_USD", "5"))
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", "50"))

# Ranker
RANK_WINDOW_DAYS = int(os.getenv("RANK_WINDOW_DAYS", "90"))
RANK_WEIGHTS = tuple(float(w) for w in os.getenv("RANK_WEIGHTS", "0.3,0.3,0.4").split(","))
RANK_CANDIDATE_POOL_SIZE = int(os.getenv("RANK_CANDIDATE_POOL_SIZE", "500"))
MIN_RESOLVED_MARKETS = int(os.getenv("MIN_RESOLVED_MARKETS", "20"))
MIN_LIFETIME_VOLUME_USD = float(os.getenv("MIN_LIFETIME_VOLUME_USD", "1000"))
MIN_LAST_TRADE_DAYS = int(os.getenv("MIN_LAST_TRADE_DAYS", "14"))

# Watcher
POLL_INTERVAL_SEC = int(os.getenv("POLL_INTERVAL_SEC", "30"))

# Storage
DB_PATH = os.getenv("DB_PATH", "data/bot.sqlite")

# Polymarket minimum order size (USDC)
MIN_ORDER_USD = 1.0
```

- [ ] **Step 6: Write `conftest.py` (shared test fixtures)**

```python
"""Shared pytest fixtures."""
import pytest
import tempfile
import os


@pytest.fixture
def tmp_db_path(tmp_path):
    """Temporary SQLite path that is auto-cleaned."""
    return str(tmp_path / "test.sqlite")


@pytest.fixture
def fixtures_dir():
    return os.path.join(os.path.dirname(__file__), "tests", "fixtures")
```

- [ ] **Step 7: Verify pytest discovery**

```bash
cd polymarket-copy-bot
python -m pip install pytest pytest-mock python-dotenv
python -m pytest --collect-only
```

Expected: `collected 0 items` (no tests yet, but pytest runs cleanly).

- [ ] **Step 8: Commit**

```bash
cd polymarket
git add polymarket-copy-bot/
git commit -m "feat(copy-bot): project scaffold + config + pytest setup"
```

---

## Task 2: Clock Abstraction

**Files:**
- Create: `polymarket-copy-bot/clock.py`
- Create: `polymarket-copy-bot/tests/test_clock.py`

**Why first:** Every other module (storage timestamps, watcher polling, executor logs) uses time. Backtest needs to inject a fake clock — must be a dependency from day 1, not retrofitted.

- [ ] **Step 1: Write the failing test**

`tests/test_clock.py`:

```python
"""Tests for clock abstraction."""
import time
from datetime import datetime, timezone
from clock import RealClock, FakeClock


def test_real_clock_now_returns_current_utc():
    c = RealClock()
    before = datetime.now(timezone.utc).timestamp()
    got = c.now().timestamp()
    after = datetime.now(timezone.utc).timestamp()
    assert before <= got <= after


def test_real_clock_sleep_actually_sleeps():
    c = RealClock()
    t0 = time.time()
    c.sleep(0.05)
    assert time.time() - t0 >= 0.05


def test_fake_clock_starts_at_given_time():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    c = FakeClock(start)
    assert c.now() == start


def test_fake_clock_sleep_advances_virtual_time():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    c = FakeClock(start)
    c.sleep(60)
    assert c.now() == datetime(2026, 1, 1, 0, 1, 0, tzinfo=timezone.utc)


def test_fake_clock_sleep_does_not_block():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    c = FakeClock(start)
    t0 = time.time()
    c.sleep(3600)
    assert time.time() - t0 < 0.05
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd polymarket-copy-bot
python -m pytest tests/test_clock.py -v
```

Expected: ImportError (no `clock` module).

- [ ] **Step 3: Implement `clock.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest tests/test_clock.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add polymarket-copy-bot/clock.py polymarket-copy-bot/tests/test_clock.py
git commit -m "feat(copy-bot): add clock abstraction (RealClock + FakeClock)"
```

---

## Task 3: Storage Layer (SQLite)

**Files:**
- Create: `polymarket-copy-bot/storage.py`
- Create: `polymarket-copy-bot/tests/test_storage.py`

Implements the 4 tables from spec §7 with the unique constraint on `our_positions(source_trader, market_id, side)`.

- [ ] **Step 1: Write the failing test**

`tests/test_storage.py`:

```python
"""Tests for SQLite storage layer."""
import pytest
from datetime import datetime, timezone
from storage import Storage, Position, TradeRow, TopTrader


def test_init_creates_all_tables(tmp_db_path):
    s = Storage(tmp_db_path)
    tables = s.list_tables()
    assert set(tables) >= {"top_10", "our_positions", "trades", "daily_pnl"}


def test_save_and_load_top_10(tmp_db_path):
    s = Storage(tmp_db_path)
    today = "2026-05-18"
    entries = [
        TopTrader(date=today, trader_addr="0xA", score=1.5, win_rate=0.7,
                  total_pnl=1000.0, sharpe_like=2.1, rank=1),
        TopTrader(date=today, trader_addr="0xB", score=1.2, win_rate=0.6,
                  total_pnl=800.0, sharpe_like=1.9, rank=2),
    ]
    s.save_top_10(today, entries)
    got = s.load_top_10(today)
    assert len(got) == 2
    assert got[0].trader_addr == "0xA"
    assert got[1].rank == 2


def test_save_top_10_replaces_existing_date(tmp_db_path):
    s = Storage(tmp_db_path)
    today = "2026-05-18"
    s.save_top_10(today, [
        TopTrader(date=today, trader_addr="0xA", score=1.0, win_rate=0.5,
                  total_pnl=100, sharpe_like=1.0, rank=1)
    ])
    s.save_top_10(today, [
        TopTrader(date=today, trader_addr="0xB", score=2.0, win_rate=0.6,
                  total_pnl=200, sharpe_like=2.0, rank=1)
    ])
    got = s.load_top_10(today)
    assert len(got) == 1
    assert got[0].trader_addr == "0xB"


def test_insert_position_returns_id(tmp_db_path):
    s = Storage(tmp_db_path)
    pid = s.insert_position(Position(
        source_trader="0xA", market_id="m1", side="YES",
        size_usd=5.0, opened_at=datetime.now(timezone.utc).isoformat(),
        status="OPEN"
    ))
    assert isinstance(pid, int)
    assert pid > 0


def test_insert_position_unique_constraint(tmp_db_path):
    s = Storage(tmp_db_path)
    p = Position(source_trader="0xA", market_id="m1", side="YES",
                 size_usd=5.0, opened_at="2026-05-18T00:00:00+00:00",
                 status="OPEN")
    s.insert_position(p)
    with pytest.raises(Exception):
        s.insert_position(p)


def test_get_open_position_by_source(tmp_db_path):
    s = Storage(tmp_db_path)
    s.insert_position(Position(
        source_trader="0xA", market_id="m1", side="YES",
        size_usd=5.0, opened_at="2026-05-18T00:00:00+00:00", status="OPEN"
    ))
    got = s.get_open_position("0xA", "m1", "YES")
    assert got is not None
    assert got.size_usd == 5.0
    assert s.get_open_position("0xA", "m999", "YES") is None


def test_close_position_records_pnl(tmp_db_path):
    s = Storage(tmp_db_path)
    pid = s.insert_position(Position(
        source_trader="0xA", market_id="m1", side="YES",
        size_usd=5.0, opened_at="2026-05-18T00:00:00+00:00", status="OPEN"
    ))
    s.close_position(pid, closed_at="2026-05-18T01:00:00+00:00",
                     realized_pnl=1.5, new_status="MIRRORED_CLOSE")
    got = s.get_position_by_id(pid)
    assert got.status == "MIRRORED_CLOSE"
    assert got.realized_pnl == 1.5


def test_record_trade(tmp_db_path):
    s = Storage(tmp_db_path)
    pid = s.insert_position(Position(
        source_trader="0xA", market_id="m1", side="YES",
        size_usd=5.0, opened_at="2026-05-18T00:00:00+00:00", status="OPEN"
    ))
    s.record_trade(TradeRow(
        position_id=pid, action="OPEN", price=0.45, size=11.1,
        tx_hash=None, ts="2026-05-18T00:00:00+00:00", dry_run=True
    ))
    trades = s.list_trades_for_position(pid)
    assert len(trades) == 1
    assert trades[0].action == "OPEN"
    assert trades[0].dry_run is True


def test_daily_pnl_accumulate(tmp_db_path):
    s = Storage(tmp_db_path)
    s.add_daily_pnl("2026-05-18", 5.0)
    s.add_daily_pnl("2026-05-18", -2.0)
    assert s.get_daily_pnl("2026-05-18") == 3.0
    assert s.get_daily_pnl("2026-05-19") == 0.0


def test_set_and_check_halted(tmp_db_path):
    s = Storage(tmp_db_path)
    assert s.is_halted("2026-05-18") is False
    s.mark_halted("2026-05-18", "2026-05-18T15:00:00+00:00")
    assert s.is_halted("2026-05-18") is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_storage.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `storage.py`**

```python
"""SQLite state store for the copy-trading bot.

4 tables (per spec §7):
  top_10         - daily ranking snapshots
  our_positions  - our mirrored positions
  trades         - audit log of every order action
  daily_pnl      - realized PnL per UTC day + halt marker
"""
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass(frozen=True)
class TopTrader:
    date: str
    trader_addr: str
    score: float
    win_rate: float
    total_pnl: float
    sharpe_like: float
    rank: int


@dataclass
class Position:
    source_trader: str
    market_id: str
    side: str  # 'YES' or 'NO'
    size_usd: float
    opened_at: str
    status: str  # OPEN | MIRRORED_CLOSE | ORPHANED_HOLD | RESOLVED
    id: Optional[int] = None
    closed_at: Optional[str] = None
    realized_pnl: Optional[float] = None


@dataclass(frozen=True)
class TradeRow:
    position_id: int
    action: str  # OPEN | CLOSE
    price: float
    size: float
    tx_hash: Optional[str]
    ts: str
    dry_run: bool


_SCHEMA = """
CREATE TABLE IF NOT EXISTS top_10 (
    date TEXT NOT NULL,
    trader_addr TEXT NOT NULL,
    score REAL NOT NULL,
    win_rate REAL NOT NULL,
    total_pnl REAL NOT NULL,
    sharpe_like REAL NOT NULL,
    rank INTEGER NOT NULL,
    PRIMARY KEY (date, trader_addr)
);

CREATE TABLE IF NOT EXISTS our_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_trader TEXT NOT NULL,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    size_usd REAL NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    realized_pnl REAL,
    status TEXT NOT NULL,
    UNIQUE (source_trader, market_id, side)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    tx_hash TEXT,
    ts TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    FOREIGN KEY (position_id) REFERENCES our_positions(id)
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    date TEXT PRIMARY KEY,
    realized_pnl REAL NOT NULL DEFAULT 0,
    halted_at TEXT
);
"""


class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def list_tables(self) -> list[str]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            return [r["name"] for r in rows]

    # --- top_10 ---
    def save_top_10(self, date: str, entries: Iterable[TopTrader]) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM top_10 WHERE date = ?", (date,))
            c.executemany(
                "INSERT INTO top_10 (date, trader_addr, score, win_rate, "
                "total_pnl, sharpe_like, rank) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(e.date, e.trader_addr, e.score, e.win_rate, e.total_pnl,
                  e.sharpe_like, e.rank) for e in entries],
            )

    def load_top_10(self, date: str) -> list[TopTrader]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM top_10 WHERE date = ? ORDER BY rank ASC",
                (date,),
            ).fetchall()
            return [TopTrader(**dict(r)) for r in rows]

    # --- positions ---
    def insert_position(self, p: Position) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO our_positions (source_trader, market_id, side, "
                "size_usd, opened_at, status) VALUES (?, ?, ?, ?, ?, ?)",
                (p.source_trader, p.market_id, p.side, p.size_usd,
                 p.opened_at, p.status),
            )
            return cur.lastrowid

    def get_open_position(self, source_trader: str, market_id: str,
                          side: str) -> Optional[Position]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM our_positions WHERE source_trader=? "
                "AND market_id=? AND side=? AND status='OPEN'",
                (source_trader, market_id, side),
            ).fetchone()
            return Position(**dict(row)) if row else None

    def get_position_by_id(self, pid: int) -> Optional[Position]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM our_positions WHERE id=?", (pid,)
            ).fetchone()
            return Position(**dict(row)) if row else None

    def close_position(self, pid: int, closed_at: str,
                       realized_pnl: float, new_status: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE our_positions SET closed_at=?, realized_pnl=?, "
                "status=? WHERE id=?",
                (closed_at, realized_pnl, new_status, pid),
            )

    def list_open_positions(self) -> list[Position]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM our_positions WHERE status='OPEN'"
            ).fetchall()
            return [Position(**dict(r)) for r in rows]

    # --- trades ---
    def record_trade(self, t: TradeRow) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO trades (position_id, action, price, size, "
                "tx_hash, ts, dry_run) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (t.position_id, t.action, t.price, t.size, t.tx_hash,
                 t.ts, 1 if t.dry_run else 0),
            )

    def list_trades_for_position(self, pid: int) -> list[TradeRow]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM trades WHERE position_id=? ORDER BY id ASC",
                (pid,),
            ).fetchall()
            return [
                TradeRow(
                    position_id=r["position_id"], action=r["action"],
                    price=r["price"], size=r["size"], tx_hash=r["tx_hash"],
                    ts=r["ts"], dry_run=bool(r["dry_run"]),
                ) for r in rows
            ]

    # --- daily_pnl ---
    def add_daily_pnl(self, date: str, delta: float) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO daily_pnl (date, realized_pnl) VALUES (?, ?) "
                "ON CONFLICT(date) DO UPDATE SET "
                "realized_pnl = realized_pnl + excluded.realized_pnl",
                (date, delta),
            )

    def get_daily_pnl(self, date: str) -> float:
        with self._conn() as c:
            row = c.execute(
                "SELECT realized_pnl FROM daily_pnl WHERE date=?", (date,)
            ).fetchone()
            return row["realized_pnl"] if row else 0.0

    def mark_halted(self, date: str, ts: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO daily_pnl (date, realized_pnl, halted_at) "
                "VALUES (?, 0, ?) ON CONFLICT(date) DO UPDATE SET halted_at=?",
                (date, ts, ts),
            )

    def is_halted(self, date: str) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT halted_at FROM daily_pnl WHERE date=?", (date,)
            ).fetchone()
            return bool(row and row["halted_at"])
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest tests/test_storage.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add polymarket-copy-bot/storage.py polymarket-copy-bot/tests/test_storage.py
git commit -m "feat(copy-bot): SQLite storage for top_10, positions, trades, daily_pnl"
```

---

## Task 4: API Client (Skeleton + Mockable)

**Files:**
- Create: `polymarket-copy-bot/api_client.py`
- Create: `polymarket-copy-bot/tests/fixtures/leaderboard.json`
- Create: `polymarket-copy-bot/tests/fixtures/activity_alice.json`
- Create: `polymarket-copy-bot/tests/fixtures/activity_bob.json`
- Create: `polymarket-copy-bot/tests/fixtures/activity_alice_t2.json`

**Note on Polymarket API:** The exact Leaderboard / Activity endpoints can shift. This task defines the **interface** (`PolymarketAPI`) and a `RequestsPolymarketAPI` implementation. Tests run against fixture JSON via a `FakeAPI`. The real endpoint URLs are isolated to one class so they can be patched when Polymarket changes them without touching business logic.

- [ ] **Step 1: Write fixtures**

`tests/fixtures/leaderboard.json`:

```json
[
  {"proxyWallet": "0xAlice", "volume": 50000, "pnl": 8000},
  {"proxyWallet": "0xBob", "volume": 30000, "pnl": 5000},
  {"proxyWallet": "0xCharlie", "volume": 500, "pnl": 100}
]
```

`tests/fixtures/activity_alice.json`:

```json
[
  {"market": "m1", "side": "YES", "type": "BUY", "size": 100,
   "price": 0.4, "timestamp": 1735689600, "resolved": true,
   "pnl_realized": 60},
  {"market": "m2", "side": "NO", "type": "BUY", "size": 50,
   "price": 0.3, "timestamp": 1736294400, "resolved": true,
   "pnl_realized": -50},
  {"market": "m3", "side": "YES", "type": "BUY", "size": 200,
   "price": 0.5, "timestamp": 1736899200, "resolved": true,
   "pnl_realized": 200}
]
```

`tests/fixtures/activity_bob.json`:

```json
[
  {"market": "m4", "side": "YES", "type": "BUY", "size": 80,
   "price": 0.6, "timestamp": 1735689600, "resolved": true,
   "pnl_realized": -10}
]
```

`tests/fixtures/activity_alice_t2.json` (alice's activity at a later poll — includes one new trade):

```json
[
  {"market": "m1", "side": "YES", "type": "BUY", "size": 100,
   "price": 0.4, "timestamp": 1735689600, "resolved": true,
   "pnl_realized": 60},
  {"market": "m2", "side": "NO", "type": "BUY", "size": 50,
   "price": 0.3, "timestamp": 1736294400, "resolved": true,
   "pnl_realized": -50},
  {"market": "m3", "side": "YES", "type": "BUY", "size": 200,
   "price": 0.5, "timestamp": 1736899200, "resolved": true,
   "pnl_realized": 200},
  {"market": "m9", "side": "YES", "type": "BUY", "size": 75,
   "price": 0.45, "timestamp": 1747569300, "resolved": false,
   "pnl_realized": null}
]
```

- [ ] **Step 2: Write the failing test**

`tests/test_api_client.py`:

```python
"""Tests for API client (focused on FakeAPI used throughout tests)."""
import json
import os
from api_client import FakeAPI, Trade


def _load(fixtures_dir, name):
    with open(os.path.join(fixtures_dir, name)) as f:
        return json.load(f)


def test_fake_api_leaderboard(fixtures_dir):
    api = FakeAPI(
        leaderboard=_load(fixtures_dir, "leaderboard.json"),
        activity_by_addr={},
    )
    lb = api.leaderboard(limit=2)
    assert len(lb) == 2
    assert lb[0].address == "0xAlice"


def test_fake_api_activity(fixtures_dir):
    api = FakeAPI(
        leaderboard=[],
        activity_by_addr={
            "0xAlice": _load(fixtures_dir, "activity_alice.json"),
        },
    )
    trades = api.user_activity("0xAlice")
    assert len(trades) == 3
    assert isinstance(trades[0], Trade)
    assert trades[0].market_id == "m1"
    assert trades[0].pnl_realized == 60
    assert trades[2].resolved is True


def test_fake_api_activity_unknown_user_empty():
    api = FakeAPI(leaderboard=[], activity_by_addr={})
    assert api.user_activity("0xNobody") == []
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python -m pytest tests/test_api_client.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement `api_client.py`**

```python
"""Polymarket API client + fake implementation for tests.

Exposes a `PolymarketAPI` Protocol with three methods used by the bot.
`RequestsPolymarketAPI` hits real endpoints; `FakeAPI` reads fixtures.
"""
from dataclasses import dataclass
from typing import Protocol, Optional
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
import config


@dataclass(frozen=True)
class LeaderboardEntry:
    address: str
    volume: float
    pnl: float


@dataclass(frozen=True)
class Trade:
    market_id: str
    side: str       # 'YES' | 'NO'
    type: str       # 'BUY' | 'SELL'
    size: float
    price: float
    timestamp: int  # unix seconds
    resolved: bool
    pnl_realized: Optional[float]


class PolymarketAPI(Protocol):
    def leaderboard(self, limit: int = 500) -> list[LeaderboardEntry]: ...
    def user_activity(self, address: str,
                      since_ts: Optional[int] = None) -> list[Trade]: ...
    def market_mid_price(self, market_id: str, side: str) -> float: ...


def _entry_from_raw(r: dict) -> LeaderboardEntry:
    return LeaderboardEntry(
        address=r["proxyWallet"],
        volume=float(r.get("volume", 0)),
        pnl=float(r.get("pnl", 0)),
    )


def _trade_from_raw(r: dict) -> Trade:
    return Trade(
        market_id=r["market"],
        side=r["side"],
        type=r["type"],
        size=float(r["size"]),
        price=float(r["price"]),
        timestamp=int(r["timestamp"]),
        resolved=bool(r.get("resolved", False)),
        pnl_realized=(
            float(r["pnl_realized"]) if r.get("pnl_realized") is not None
            else None
        ),
    )


class RequestsPolymarketAPI:
    """Real implementation. Endpoint paths are isolated here so a Polymarket
    schema change only touches this class."""

    def __init__(self, base_data_api: str = config.DATA_API,
                 base_clob_api: str = config.CLOB_API):
        self.data_api = base_data_api
        self.clob_api = base_clob_api

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=1, max=10))
    def _get(self, url: str, params: dict | None = None) -> list | dict:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def leaderboard(self, limit: int = 500) -> list[LeaderboardEntry]:
        # Polymarket exposes a leaderboard endpoint; the exact path may evolve.
        # Centralized here for easy patching.
        raw = self._get(f"{self.data_api}/leaderboard",
                        params={"window": "all", "limit": limit})
        if isinstance(raw, dict) and "data" in raw:
            raw = raw["data"]
        return [_entry_from_raw(r) for r in raw]

    def user_activity(self, address: str,
                      since_ts: Optional[int] = None) -> list[Trade]:
        params = {"user": address, "limit": 500}
        if since_ts is not None:
            params["since"] = since_ts
        raw = self._get(f"{self.data_api}/activity", params=params)
        if isinstance(raw, dict) and "data" in raw:
            raw = raw["data"]
        return [_trade_from_raw(r) for r in raw]

    def market_mid_price(self, market_id: str, side: str) -> float:
        raw = self._get(f"{self.clob_api}/midpoint",
                        params={"market": market_id, "side": side})
        return float(raw["mid"]) if isinstance(raw, dict) else float(raw)


class FakeAPI:
    """In-memory fake for tests and backtest replay."""

    def __init__(self, leaderboard: list[dict],
                 activity_by_addr: dict[str, list[dict]],
                 prices: dict[tuple[str, str], float] | None = None):
        self._leaderboard = [_entry_from_raw(r) for r in leaderboard]
        self._activity = {
            addr: [_trade_from_raw(r) for r in trades]
            for addr, trades in activity_by_addr.items()
        }
        self._prices = prices or {}

    def leaderboard(self, limit: int = 500) -> list[LeaderboardEntry]:
        return self._leaderboard[:limit]

    def user_activity(self, address: str,
                      since_ts: Optional[int] = None) -> list[Trade]:
        trades = self._activity.get(address, [])
        if since_ts is not None:
            trades = [t for t in trades if t.timestamp >= since_ts]
        return list(trades)

    def market_mid_price(self, market_id: str, side: str) -> float:
        return self._prices.get((market_id, side), 0.5)

    # Test helpers — only used by tests
    def set_activity(self, address: str, trades: list[dict]) -> None:
        self._activity[address] = [_trade_from_raw(r) for r in trades]

    def set_price(self, market_id: str, side: str, price: float) -> None:
        self._prices[(market_id, side)] = price
```

- [ ] **Step 5: Run tests to verify pass**

```bash
python -m pytest tests/test_api_client.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add polymarket-copy-bot/api_client.py polymarket-copy-bot/tests/test_api_client.py polymarket-copy-bot/tests/fixtures/
git commit -m "feat(copy-bot): API client with PolymarketAPI protocol + FakeAPI"
```

---

## Task 5: Ranker (Composite Scoring)

**Files:**
- Create: `polymarket-copy-bot/ranker.py`
- Create: `polymarket-copy-bot/tests/test_ranker.py`

Implements spec §4: candidate filtering → 3 raw indicators → z-score → weighted sum → top 10.

- [ ] **Step 1: Write the failing test**

`tests/test_ranker.py`:

```python
"""Tests for ranker."""
import json
import os
import pytest
from datetime import datetime, timezone
from api_client import FakeAPI
from clock import FakeClock
from ranker import Ranker, RawMetrics, _z_scores


def _load(fixtures_dir, name):
    with open(os.path.join(fixtures_dir, name)) as f:
        return json.load(f)


def test_z_scores_zero_when_all_equal():
    z = _z_scores([5.0, 5.0, 5.0])
    assert all(v == 0.0 for v in z)


def test_z_scores_standard():
    z = _z_scores([1.0, 2.0, 3.0])
    # mean=2, std=sqrt(2/3)
    assert z[1] == pytest.approx(0.0, abs=1e-6)
    assert z[0] < 0 and z[2] > 0


def test_filter_rejects_low_sample_count():
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    metrics = RawMetrics(
        address="0xX", resolved_count=10, lifetime_volume=5000,
        last_trade_ts=int(datetime(2026, 5, 17, tzinfo=timezone.utc).timestamp()),
        win_rate=0.9, total_pnl=1000, sharpe_like=2.0,
    )
    assert r._passes_filter(metrics) is False


def test_filter_rejects_low_volume():
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    metrics = RawMetrics(
        address="0xX", resolved_count=50, lifetime_volume=500,
        last_trade_ts=int(datetime(2026, 5, 17, tzinfo=timezone.utc).timestamp()),
        win_rate=0.9, total_pnl=1000, sharpe_like=2.0,
    )
    assert r._passes_filter(metrics) is False


def test_filter_rejects_stale_trader():
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(now))
    metrics = RawMetrics(
        address="0xX", resolved_count=50, lifetime_volume=5000,
        last_trade_ts=int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp()),  # 47 days ago
        win_rate=0.9, total_pnl=1000, sharpe_like=2.0,
    )
    assert r._passes_filter(metrics) is False


def test_filter_passes_good_candidate():
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    r = Ranker(api=FakeAPI([], {}), clock=FakeClock(now))
    metrics = RawMetrics(
        address="0xX", resolved_count=50, lifetime_volume=5000,
        last_trade_ts=int(datetime(2026, 5, 17, tzinfo=timezone.utc).timestamp()),
        win_rate=0.6, total_pnl=2000, sharpe_like=1.5,
    )
    assert r._passes_filter(metrics) is True


def test_compute_metrics_from_activity(fixtures_dir):
    """alice has 3 resolved trades: +60, -50, +200 → 2/3 win, 210 total"""
    api = FakeAPI(
        leaderboard=_load(fixtures_dir, "leaderboard.json"),
        activity_by_addr={
            "0xAlice": _load(fixtures_dir, "activity_alice.json"),
        },
    )
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    r = Ranker(api=api, clock=FakeClock(now))
    m = r._compute_metrics("0xAlice")
    assert m.resolved_count == 3
    assert m.win_rate == pytest.approx(2 / 3)
    assert m.total_pnl == 210


def test_rank_end_to_end(fixtures_dir, monkeypatch):
    """Run full pipeline against 2 candidates; verify ordering."""
    api = FakeAPI(
        leaderboard=_load(fixtures_dir, "leaderboard.json"),
        activity_by_addr={
            "0xAlice": _load(fixtures_dir, "activity_alice.json"),
            "0xBob": _load(fixtures_dir, "activity_bob.json"),
        },
    )
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    # Loosen filters so the small fixture data passes
    monkeypatch.setattr("ranker.MIN_RESOLVED_MARKETS", 1)
    monkeypatch.setattr("ranker.MIN_LIFETIME_VOLUME_USD", 0)
    r = Ranker(api=api, clock=FakeClock(now))
    top = r.compute_top_n(n=2)
    assert len(top) >= 1
    assert top[0].trader_addr in ("0xAlice", "0xBob")
    # Alice has higher PnL and win-rate, should rank first
    if len(top) == 2:
        assert top[0].trader_addr == "0xAlice"
        assert top[0].rank == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_ranker.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `ranker.py`**

```python
"""Composite-score ranker.

Selects top-N Polymarket traders by a weighted z-score of:
  - win_rate
  - total_pnl
  - sharpe_like (mean / std of per-market ROI)
"""
import math
import statistics
from dataclasses import dataclass
from typing import Optional
from api_client import PolymarketAPI, Trade
from clock import Clock
from storage import Storage, TopTrader
from config import (
    RANK_WINDOW_DAYS, RANK_WEIGHTS, RANK_CANDIDATE_POOL_SIZE,
    MIN_RESOLVED_MARKETS, MIN_LIFETIME_VOLUME_USD, MIN_LAST_TRADE_DAYS,
)


@dataclass(frozen=True)
class RawMetrics:
    address: str
    resolved_count: int
    lifetime_volume: float
    last_trade_ts: int
    win_rate: float
    total_pnl: float
    sharpe_like: float


def _z_scores(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    mu = statistics.mean(values)
    sigma = statistics.pstdev(values)
    if sigma == 0:
        return [0.0] * len(values)
    return [(v - mu) / sigma for v in values]


class Ranker:
    def __init__(self, api: PolymarketAPI, clock: Clock,
                 storage: Optional[Storage] = None):
        self.api = api
        self.clock = clock
        self.storage = storage

    def _passes_filter(self, m: RawMetrics) -> bool:
        if m.resolved_count < MIN_RESOLVED_MARKETS:
            return False
        if m.lifetime_volume < MIN_LIFETIME_VOLUME_USD:
            return False
        now_ts = int(self.clock.now().timestamp())
        if now_ts - m.last_trade_ts > MIN_LAST_TRADE_DAYS * 86400:
            return False
        return True

    def _compute_metrics(self, address: str) -> RawMetrics:
        window_start = int(self.clock.now().timestamp()) - RANK_WINDOW_DAYS * 86400
        trades: list[Trade] = self.api.user_activity(address,
                                                     since_ts=window_start)
        resolved = [t for t in trades if t.resolved
                    and t.pnl_realized is not None]
        wins = sum(1 for t in resolved if t.pnl_realized > 0)
        total_pnl = sum(t.pnl_realized for t in resolved)
        # ROI per market: pnl / cost  (cost = size * price)
        rois: list[float] = []
        for t in resolved:
            cost = t.size * t.price
            if cost > 0:
                rois.append(t.pnl_realized / cost)
        if len(rois) >= 2 and statistics.pstdev(rois) > 0:
            sharpe = statistics.mean(rois) / statistics.pstdev(rois)
        else:
            sharpe = 0.0
        lifetime_volume = sum(t.size * t.price for t in trades)
        last_ts = max((t.timestamp for t in trades), default=0)
        win_rate = (wins / len(resolved)) if resolved else 0.0
        return RawMetrics(
            address=address,
            resolved_count=len(resolved),
            lifetime_volume=lifetime_volume,
            last_trade_ts=last_ts,
            win_rate=win_rate,
            total_pnl=total_pnl,
            sharpe_like=sharpe,
        )

    def compute_top_n(self, n: int = 10) -> list[TopTrader]:
        date_str = self.clock.now().date().isoformat()
        candidates = self.api.leaderboard(limit=RANK_CANDIDATE_POOL_SIZE)
        metrics = [self._compute_metrics(c.address) for c in candidates]
        passing = [m for m in metrics if self._passes_filter(m)]
        if not passing:
            return []
        z_win = _z_scores([m.win_rate for m in passing])
        z_pnl = _z_scores([m.total_pnl for m in passing])
        z_sharpe = _z_scores([m.sharpe_like for m in passing])
        w1, w2, w3 = RANK_WEIGHTS
        scored = []
        for i, m in enumerate(passing):
            score = w1 * z_win[i] + w2 * z_pnl[i] + w3 * z_sharpe[i]
            scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:n]
        return [
            TopTrader(
                date=date_str, trader_addr=m.address, score=score,
                win_rate=m.win_rate, total_pnl=m.total_pnl,
                sharpe_like=m.sharpe_like, rank=rank,
            )
            for rank, (score, m) in enumerate(top, start=1)
        ]

    def rank_and_persist(self, n: int = 10) -> list[TopTrader]:
        if self.storage is None:
            raise RuntimeError("storage required for persistence")
        top = self.compute_top_n(n)
        date_str = self.clock.now().date().isoformat()
        self.storage.save_top_10(date_str, top)
        return top
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest tests/test_ranker.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add polymarket-copy-bot/ranker.py polymarket-copy-bot/tests/test_ranker.py
git commit -m "feat(copy-bot): ranker with z-score weighted composite scoring"
```

---

## Task 6: Watcher (Activity Diff → Events)

**Files:**
- Create: `polymarket-copy-bot/watcher.py`
- Create: `polymarket-copy-bot/tests/test_watcher.py`

Watcher polls each top-10 trader's activity, diffs against the last poll, and emits `Event(kind=OPEN|CLOSE, ...)`. Crucially: spec §3 row 3 — exits from traders **no longer in top 10** are ignored (we don't mirror them).

- [ ] **Step 1: Write the failing test**

`tests/test_watcher.py`:

```python
"""Tests for watcher."""
import json
import os
from datetime import datetime, timezone
from api_client import FakeAPI
from clock import FakeClock
from watcher import Watcher, Event


def _load(fixtures_dir, name):
    with open(os.path.join(fixtures_dir, name)) as f:
        return json.load(f)


def test_first_poll_emits_no_events(fixtures_dir):
    """The first poll establishes baseline; nothing is 'new'."""
    api = FakeAPI(
        leaderboard=[],
        activity_by_addr={"0xAlice": _load(fixtures_dir, "activity_alice.json")},
    )
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    events = w.poll(top_addresses=["0xAlice"])
    assert events == []


def test_second_poll_detects_new_open(fixtures_dir):
    api = FakeAPI(
        leaderboard=[],
        activity_by_addr={"0xAlice": _load(fixtures_dir, "activity_alice.json")},
    )
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    w.poll(top_addresses=["0xAlice"])  # baseline
    api.set_activity("0xAlice", _load(fixtures_dir, "activity_alice_t2.json"))
    events = w.poll(top_addresses=["0xAlice"])
    assert len(events) == 1
    e = events[0]
    assert e.kind == "OPEN"
    assert e.source_trader == "0xAlice"
    assert e.market_id == "m9"
    assert e.side == "YES"
    assert e.price == 0.45


def test_detects_close_when_position_disappears(fixtures_dir):
    """If a trader holds a position then exits, watcher emits CLOSE."""
    initial = [{
        "market": "mX", "side": "YES", "type": "BUY", "size": 100,
        "price": 0.4, "timestamp": 1747569000, "resolved": False,
        "pnl_realized": None,
    }]
    after = [{
        "market": "mX", "side": "YES", "type": "BUY", "size": 100,
        "price": 0.4, "timestamp": 1747569000, "resolved": False,
        "pnl_realized": None,
    }, {
        "market": "mX", "side": "YES", "type": "SELL", "size": 100,
        "price": 0.55, "timestamp": 1747569300, "resolved": False,
        "pnl_realized": None,
    }]
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": initial})
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    w.poll(top_addresses=["0xA"])
    api.set_activity("0xA", after)
    events = w.poll(top_addresses=["0xA"])
    assert len(events) == 1
    assert events[0].kind == "CLOSE"
    assert events[0].market_id == "mX"
    assert events[0].price == 0.55


def test_close_ignored_when_trader_not_in_top10(fixtures_dir):
    """E1 rule: trader dropped from top 10 → ignore their exits."""
    initial = [{
        "market": "mX", "side": "YES", "type": "BUY", "size": 100,
        "price": 0.4, "timestamp": 1747569000, "resolved": False,
        "pnl_realized": None,
    }]
    after = initial + [{
        "market": "mX", "side": "YES", "type": "SELL", "size": 100,
        "price": 0.55, "timestamp": 1747569300, "resolved": False,
        "pnl_realized": None,
    }]
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": initial})
    w = Watcher(api=api, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)))
    w.poll(top_addresses=["0xA"])  # in top 10
    api.set_activity("0xA", after)
    events = w.poll(top_addresses=[])  # dropped from top 10
    assert events == []  # CLOSE suppressed
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_watcher.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `watcher.py`**

```python
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
                    # Only mirror exits for current top-10 traders
                    if addr in top_set:
                        events.append(Event(
                            kind="CLOSE", source_trader=addr,
                            market_id=t.market_id, side=t.side,
                            price=t.price, timestamp=t.timestamp,
                        ))
            self._seen[addr] = current_fps
        return events
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest tests/test_watcher.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add polymarket-copy-bot/watcher.py polymarket-copy-bot/tests/test_watcher.py
git commit -m "feat(copy-bot): activity-diffing watcher emitting OPEN/CLOSE events"
```

---

## Task 7: RiskGate (Daily Loss Circuit Breaker)

**Files:**
- Create: `polymarket-copy-bot/risk.py`
- Create: `polymarket-copy-bot/tests/test_risk.py`

Per spec §3 last row: when daily loss ≥ limit, **reject opens but allow exits**.

- [ ] **Step 1: Write the failing test**

`tests/test_risk.py`:

```python
"""Tests for the daily-loss risk gate."""
from datetime import datetime, timezone
from clock import FakeClock
from storage import Storage
from risk import RiskGate


def test_allows_open_when_below_limit(tmp_db_path):
    s = Storage(tmp_db_path)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    assert g.allow_open() is True


def test_blocks_open_when_at_limit(tmp_db_path):
    s = Storage(tmp_db_path)
    s.add_daily_pnl("2026-05-18", -50.0)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    assert g.allow_open() is False


def test_blocks_open_when_over_limit(tmp_db_path):
    s = Storage(tmp_db_path)
    s.add_daily_pnl("2026-05-18", -75.0)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    assert g.allow_open() is False


def test_always_allows_close(tmp_db_path):
    s = Storage(tmp_db_path)
    s.add_daily_pnl("2026-05-18", -200.0)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    assert g.allow_close() is True


def test_record_pnl_writes_storage(tmp_db_path):
    s = Storage(tmp_db_path)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    g.record_realized_pnl(-10.0)
    g.record_realized_pnl(-15.0)
    assert s.get_daily_pnl("2026-05-18") == -25.0


def test_halt_persisted_after_breach(tmp_db_path):
    s = Storage(tmp_db_path)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 18, tzinfo=timezone.utc)), daily_loss_limit=50)
    g.record_realized_pnl(-60.0)
    g.allow_open()  # triggers halt-marker
    assert s.is_halted("2026-05-18") is True


def test_day_rollover_resets_check(tmp_db_path):
    s = Storage(tmp_db_path)
    s.add_daily_pnl("2026-05-18", -100.0)
    g = RiskGate(storage=s, clock=FakeClock(
        datetime(2026, 5, 19, tzinfo=timezone.utc)), daily_loss_limit=50)
    assert g.allow_open() is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_risk.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `risk.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest tests/test_risk.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add polymarket-copy-bot/risk.py polymarket-copy-bot/tests/test_risk.py
git commit -m "feat(copy-bot): daily loss circuit breaker (blocks opens, allows closes)"
```

---

## Task 8: Executor (Dry-Run + Live Stub)

**Files:**
- Create: `polymarket-copy-bot/executor.py`
- Create: `polymarket-copy-bot/tests/test_executor.py`

Two implementations:
- `DryRunExecutor` — logs trades, persists to storage with `dry_run=True`, never calls CLOB
- `LiveExecutor` — wraps `ClobClient`, places real orders

Both go through the same `handle_event(Event)` interface so the watcher loop is agnostic.

- [ ] **Step 1: Write the failing test**

`tests/test_executor.py`:

```python
"""Tests for the executor (DryRunExecutor)."""
from datetime import datetime, timezone
from api_client import FakeAPI
from clock import FakeClock
from storage import Storage, Position
from risk import RiskGate
from watcher import Event
from executor import DryRunExecutor


def _make_executor(tmp_db_path, prices=None, loss_limit=50.0):
    s = Storage(tmp_db_path)
    api = FakeAPI(leaderboard=[], activity_by_addr={}, prices=prices or {})
    clock = FakeClock(datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc))
    gate = RiskGate(storage=s, clock=clock, daily_loss_limit=loss_limit)
    ex = DryRunExecutor(storage=s, api=api, clock=clock, gate=gate,
                        copy_amount_usd=5.0, min_order_usd=1.0)
    return ex, s, api


def test_open_event_creates_position(tmp_db_path):
    ex, s, api = _make_executor(tmp_db_path,
                                prices={("m1", "YES"): 0.5})
    api.set_price("m1", "YES", 0.5)
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m1", side="YES", price=0.5,
                          timestamp=1747569300))
    open_pos = s.list_open_positions()
    assert len(open_pos) == 1
    assert open_pos[0].source_trader == "0xA"
    assert open_pos[0].market_id == "m1"
    assert open_pos[0].size_usd == 5.0


def test_open_logs_trade_with_dry_run_flag(tmp_db_path):
    ex, s, _ = _make_executor(tmp_db_path)
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m1", side="YES", price=0.5,
                          timestamp=1747569300))
    pos = s.list_open_positions()[0]
    trades = s.list_trades_for_position(pos.id)
    assert len(trades) == 1
    assert trades[0].action == "OPEN"
    assert trades[0].dry_run is True


def test_open_rejected_by_risk_gate(tmp_db_path):
    ex, s, _ = _make_executor(tmp_db_path, loss_limit=10.0)
    s.add_daily_pnl("2026-05-18", -15.0)  # already past limit
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m1", side="YES", price=0.5,
                          timestamp=1747569300))
    assert s.list_open_positions() == []


def test_open_skipped_when_already_holding(tmp_db_path):
    """Same source_trader + market + side → no duplicate open
    (spec §5: only follow first opening)."""
    ex, s, _ = _make_executor(tmp_db_path)
    e = Event(kind="OPEN", source_trader="0xA", market_id="m1",
              side="YES", price=0.5, timestamp=1747569300)
    ex.handle_event(e)
    ex.handle_event(e)
    assert len(s.list_open_positions()) == 1


def test_close_event_closes_matching_position(tmp_db_path):
    ex, s, api = _make_executor(tmp_db_path)
    ex.handle_event(Event(kind="OPEN", source_trader="0xA",
                          market_id="m1", side="YES", price=0.4,
                          timestamp=1747569000))
    ex.handle_event(Event(kind="CLOSE", source_trader="0xA",
                          market_id="m1", side="YES", price=0.55,
                          timestamp=1747569300))
    open_pos = s.list_open_positions()
    assert open_pos == []
    # Verify position now closed with realized_pnl > 0
    # size_usd = 5, bought at 0.4 → shares = 12.5; sold at 0.55 → 6.875; pnl = 1.875
    # Look up the closed position
    import sqlite3
    conn = sqlite3.connect(tmp_db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM our_positions WHERE source_trader='0xA'"
                       ).fetchone()
    assert row["status"] == "MIRRORED_CLOSE"
    assert row["realized_pnl"] > 0


def test_close_without_matching_position_is_noop(tmp_db_path):
    ex, s, _ = _make_executor(tmp_db_path)
    ex.handle_event(Event(kind="CLOSE", source_trader="0xZ",
                          market_id="m999", side="YES", price=0.5,
                          timestamp=1747569300))
    # No exception, no state change
    assert s.list_open_positions() == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_executor.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `executor.py`**

```python
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
        # PnL = (sell_price - buy_price) * shares
        # shares = pos.size_usd / open_price; need open price
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
                token_id=e.market_id,  # caller must pass token_id as market_id
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
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest tests/test_executor.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest -v
```

Expected: All passing (clock 5 + storage 10 + api 3 + ranker 8 + watcher 4 + risk 7 + executor 6 = 43 tests).

- [ ] **Step 6: Commit**

```bash
git add polymarket-copy-bot/executor.py polymarket-copy-bot/tests/test_executor.py
git commit -m "feat(copy-bot): DryRunExecutor + LiveExecutor with risk gate"
```

---

## Task 9: Main CLI

**Files:**
- Create: `polymarket-copy-bot/main.py`
- Create: `polymarket-copy-bot/tests/test_main_cli.py`

CLI subcommands: `rank`, `watch --dry-run|--live`, `backtest --days N`.

- [ ] **Step 1: Write the failing test**

`tests/test_main_cli.py`:

```python
"""Tests for the CLI entry point."""
import subprocess
import sys
import os


def _run(*args, cwd):
    return subprocess.run(
        [sys.executable, "main.py", *args],
        cwd=cwd, capture_output=True, text=True, timeout=10,
    )


def test_cli_help(tmp_path, monkeypatch):
    # Run from polymarket-copy-bot dir
    bot_dir = os.path.join(os.path.dirname(__file__), "..")
    result = _run("--help", cwd=bot_dir)
    assert result.returncode == 0
    assert "rank" in result.stdout
    assert "watch" in result.stdout
    assert "backtest" in result.stdout


def test_cli_watch_requires_mode(tmp_path):
    bot_dir = os.path.join(os.path.dirname(__file__), "..")
    result = _run("watch", cwd=bot_dir)
    # Should fail without --dry-run or --live
    assert result.returncode != 0


def test_cli_live_requires_confirmation_env(tmp_path, monkeypatch):
    """--live without CONFIRM_LIVE=yes should refuse to run."""
    bot_dir = os.path.join(os.path.dirname(__file__), "..")
    env = os.environ.copy()
    env.pop("CONFIRM_LIVE", None)
    result = subprocess.run(
        [sys.executable, "main.py", "watch", "--live"],
        cwd=bot_dir, capture_output=True, text=True, timeout=10, env=env,
    )
    assert result.returncode != 0
    assert "CONFIRM_LIVE" in (result.stdout + result.stderr)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_main_cli.py -v
```

Expected: ImportError or FileNotFound for `main.py`.

- [ ] **Step 3: Implement `main.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest tests/test_main_cli.py -v
```

Expected: 3 passed. (The `backtest.py` import in `cmd_backtest` is only resolved when invoked, so missing-module errors won't show up here.)

- [ ] **Step 5: Commit**

```bash
git add polymarket-copy-bot/main.py polymarket-copy-bot/tests/test_main_cli.py
git commit -m "feat(copy-bot): CLI with rank / watch / backtest subcommands"
```

---

## Task 10: Backtest Engine

**Files:**
- Create: `polymarket-copy-bot/backtest.py`
- Create: `polymarket-copy-bot/tests/test_backtest.py`

Per spec §8: replay historical activity through the same Watcher → Executor pipeline. Replaces `FakeClock` advance + `FakeAPI` activity injection over time. **No** new strategy code paths.

- [ ] **Step 1: Write the failing test**

`tests/test_backtest.py`:

```python
"""Tests for backtest engine."""
from datetime import datetime, timezone
from backtest import BacktestEngine
from api_client import FakeAPI, Trade
from clock import FakeClock
from storage import Storage


def test_backtest_replays_trades_in_order(tmp_db_path):
    """Two trades over time → both mirrored, PnL accumulated."""
    # Alice's full activity (chronological)
    raw = [
        {"market": "m1", "side": "YES", "type": "BUY", "size": 100,
         "price": 0.4, "timestamp": 1747000000, "resolved": False,
         "pnl_realized": None},
        {"market": "m1", "side": "YES", "type": "SELL", "size": 100,
         "price": 0.55, "timestamp": 1747000600, "resolved": False,
         "pnl_realized": None},
    ]
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": raw})
    storage = Storage(tmp_db_path)
    start = datetime.fromtimestamp(1746999000, tz=timezone.utc)
    clock = FakeClock(start)
    eng = BacktestEngine(
        api=api, storage=storage, clock=clock,
        top_addresses=["0xA"], copy_amount_usd=5.0, daily_loss_limit=50.0,
        poll_interval_sec=300, total_seconds=2000,
    )
    pnl, n_trades = eng.run()
    assert n_trades == 2  # one OPEN + one CLOSE
    assert pnl > 0  # 5/0.4 * (0.55-0.4) = 1.875


def test_backtest_respects_loss_limit(tmp_db_path):
    """Once limit breached, no new opens."""
    raw = [
        {"market": "m1", "side": "YES", "type": "BUY", "size": 100,
         "price": 0.5, "timestamp": 1747000000, "resolved": False,
         "pnl_realized": None},
        {"market": "m1", "side": "YES", "type": "SELL", "size": 100,
         "price": 0.1, "timestamp": 1747000600, "resolved": False,
         "pnl_realized": None},
        {"market": "m2", "side": "YES", "type": "BUY", "size": 100,
         "price": 0.5, "timestamp": 1747001200, "resolved": False,
         "pnl_realized": None},
    ]
    api = FakeAPI(leaderboard=[], activity_by_addr={"0xA": raw})
    storage = Storage(tmp_db_path)
    start = datetime.fromtimestamp(1746999000, tz=timezone.utc)
    clock = FakeClock(start)
    eng = BacktestEngine(
        api=api, storage=storage, clock=clock,
        top_addresses=["0xA"], copy_amount_usd=5.0,
        daily_loss_limit=1.0,   # tiny limit
        poll_interval_sec=300, total_seconds=3000,
    )
    pnl, n_trades = eng.run()
    # OPEN m1, CLOSE m1 (loss > $1 → halt), OPEN m2 blocked
    assert n_trades == 2
    assert pnl < 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_backtest.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `backtest.py`**

```python
"""Backtest engine.

Replays historical activity through the SAME Watcher → RiskGate → Executor
path used in live mode. Time is virtual (FakeClock). API is FakeAPI seeded
with full historical data.

For simplicity the engine treats the activity passed in as already-historical;
the `total_seconds` parameter just bounds how long to "run" the virtual clock
forward in poll-sized increments.
"""
from typing import Optional
from api_client import FakeAPI, PolymarketAPI
from clock import FakeClock
from storage import Storage
from risk import RiskGate
from watcher import Watcher
from executor import DryRunExecutor


class BacktestEngine:
    def __init__(self, api: PolymarketAPI, storage: Storage, clock: FakeClock,
                 top_addresses: list[str], copy_amount_usd: float,
                 daily_loss_limit: float, poll_interval_sec: int,
                 total_seconds: int):
        self.api = api
        self.storage = storage
        self.clock = clock
        self.top_addresses = top_addresses
        self.poll_interval = poll_interval_sec
        self.total_seconds = total_seconds
        self.gate = RiskGate(storage=storage, clock=clock,
                             daily_loss_limit=daily_loss_limit)
        self.watcher = Watcher(api=api, clock=clock)
        self.executor = DryRunExecutor(
            storage=storage, api=api, clock=clock, gate=self.gate,
            copy_amount_usd=copy_amount_usd, min_order_usd=1.0,
        )

    def run(self) -> tuple[float, int]:
        elapsed = 0
        trade_count = 0
        while elapsed < self.total_seconds:
            events = self.watcher.poll(self.top_addresses)
            for ev in events:
                self.executor.handle_event(ev)
                trade_count += 1
            self.clock.sleep(self.poll_interval)
            elapsed += self.poll_interval
        # Total realized PnL across all closed positions
        positions = []
        import sqlite3
        conn = sqlite3.connect(self.storage.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT realized_pnl FROM our_positions WHERE realized_pnl IS NOT NULL"
        ).fetchall()
        total_pnl = sum(r["realized_pnl"] for r in rows)
        return total_pnl, trade_count


def run_backtest(days: int, db_path: str = ":memory:") -> tuple[float, int]:
    """Convenience wrapper invoked by `main.py backtest`.

    First version: pulls real activity for the *current* stored top_10 from
    the Data-API over the last `days` days, runs replay. Production users
    can seed bot.sqlite with a known top_10 row before invoking.
    """
    from datetime import datetime, timezone, timedelta
    from api_client import RequestsPolymarketAPI
    real_api = RequestsPolymarketAPI()
    real_storage = Storage("data/bot.sqlite")  # source of top_10
    today = datetime.now(timezone.utc).date().isoformat()
    top = real_storage.load_top_10(today)
    if not top:
        raise RuntimeError(
            "No top_10 found for today — run `main.py rank` first."
        )
    since_ts = int((datetime.now(timezone.utc)
                    - timedelta(days=days)).timestamp())
    activity_by_addr = {}
    for t in top:
        trades = real_api.user_activity(t.trader_addr, since_ts=since_ts)
        activity_by_addr[t.trader_addr] = [
            {
                "market": tr.market_id, "side": tr.side, "type": tr.type,
                "size": tr.size, "price": tr.price,
                "timestamp": tr.timestamp, "resolved": tr.resolved,
                "pnl_realized": tr.pnl_realized,
            }
            for tr in trades
        ]
    fake_api = FakeAPI(leaderboard=[], activity_by_addr=activity_by_addr)
    start = datetime.fromtimestamp(since_ts, tz=timezone.utc)
    clock = FakeClock(start)
    bt_storage = Storage(db_path)
    eng = BacktestEngine(
        api=fake_api, storage=bt_storage, clock=clock,
        top_addresses=[t.trader_addr for t in top],
        copy_amount_usd=5.0, daily_loss_limit=50.0,
        poll_interval_sec=300, total_seconds=days * 86400,
    )
    return eng.run()
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest tests/test_backtest.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest -v
```

Expected: 48 tests passing (43 from earlier + 2 backtest + 3 cli).

- [ ] **Step 6: Commit**

```bash
git add polymarket-copy-bot/backtest.py polymarket-copy-bot/tests/test_backtest.py
git commit -m "feat(copy-bot): backtest engine sharing live pipeline"
```

---

## Task 11: README + Risk Documentation

**Files:**
- Create: `polymarket-copy-bot/README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Polymarket 跟单交易机器人

每日筛选 Polymarket 上 top 10 高水平交易员（复合分：胜率 + 累计盈利 + 风险调整 ROI），实时跟随他们的开仓和平仓。

> **设计文档**：`../docs/superpowers/specs/2026-05-18-polymarket-copy-bot-design.md`

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 POLYMARKET_PRIVATE_KEY 和 POLYMARKET_FUNDER_ADDRESS

# 1. 跑一次排名（写入今日 top_10）
python main.py rank

# 2. DRY-RUN 跟单（不下单，只打日志）
python main.py watch --dry-run

# 3. 实盘（需要环境变量确认）
CONFIRM_LIVE=yes python main.py watch --live

# 4. 回测（过去 60 天）
python main.py backtest --days 60
```

## 工作流程建议

1. **第一周**：每日 cron 跑 `rank`，运行 `watch --dry-run` 累积观察数据
2. **第二周**：用 `backtest` 验证策略，根据结果调整 `RANK_WEIGHTS`
3. **第三周起**：小额开实盘（`COPY_AMOUNT_USD=2`），观察实盘和回测的差距
4. **稳定后**：调高 `COPY_AMOUNT_USD`

## 风控说明（重要）

本机器人**只有一个硬风控**：`DAILY_LOSS_LIMIT`（日已实现亏损上限）。

**未启用的风控**（设计上的取舍）：
- **最大并发持仓数**：理论上 10 个 top trader 同时疯狂开仓可能堆出几十个仓位
- **单交易员最大敞口**：某个 top trader 一天连开 30 单，你按固定 $5 跟会有 $150 暴露

这些故意省略，以保持配置最简。`DAILY_LOSS_LIMIT` 作为事后熔断兜底——一旦今日已实现亏损达到上限，**新开仓被拒绝，但平仓继续允许**（让你能止损）。

代价：可能在熔断触发前已亏满当日上限。如果实盘运行中发现频繁触发熔断，请考虑在 `risk.py` 中加入：
- `MAX_OPEN_POSITIONS` 检查
- 单 source_trader 累计敞口检查

## 配置参考

见 `.env.example`。关键参数：

| 变量 | 默认 | 说明 |
|------|------|------|
| `COPY_AMOUNT_USD` | 5 | 每笔跟单的固定美元金额 |
| `DAILY_LOSS_LIMIT` | 50 | 日已实现亏损上限（熔断阈值） |
| `RANK_WEIGHTS` | 0.3,0.3,0.4 | win_rate / total_pnl / sharpe 权重 |
| `RANK_WINDOW_DAYS` | 90 | 评分窗口 |
| `POLL_INTERVAL_SEC` | 30 | 检测新单延迟 |

## 测试

```bash
python -m pytest -v
```

## 已知局限

- 回测**不模拟**：滑点、挂单未成交、网络延迟、Polymarket 临时下架市场。实盘 PnL 大概率低于回测。
- 同一 source_trader 对同一市场连续加仓时，本机器人**只跟第一次**（避免你的固定金额策略和对方加仓策略冲突）。
- Polymarket 官方 Leaderboard / Activity API 的具体端点可能变动；URL 集中在 `api_client.py::RequestsPolymarketAPI` 一处。

## 与 polymarket-arb-bot 的关系

并列的独立项目。共用同一个钱包（`.env` 配置可复制），但策略逻辑完全独立。
```

- [ ] **Step 2: Commit**

```bash
git add polymarket-copy-bot/README.md
git commit -m "docs(copy-bot): README with quickstart, risk model, and known limitations"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Implemented in |
|---|---|
| §1 Goals | All tasks (negative space: no arb logic) |
| §2 Decisions A1/B1/C1/D1/E1/F1/G2 | Task 5 (D1 ranking), Task 6 (E1 ignore-dropouts), Task 7 (G2), Task 8 (A1/B1/C1), Task 9 (F1 poll loop) |
| §3 Components diagram | Tasks 3-10 |
| §3 Trigger table | Task 6 (events) + Task 8 (handlers) + Task 7 (allow_close always true) |
| §4 Composite formula | Task 5 |
| §5 Position lifecycle | Task 3 (Position dataclass + states), Task 8 (state transitions) |
| §6 Project structure | Task 1 + per-task files |
| §6 CLI | Task 9 |
| §7 SQLite schema | Task 3 |
| §8 Backtest | Task 10 |
| §9 Failure modes | Task 4 (tenacity retry), Task 7 (halt), Task 8 (dedup), Task 11 (docs) |
| §10 Out of scope | Not implemented (correct) |

**Placeholder scan:** Searched for TBD/TODO/"implement later"/"appropriate"/"similar to" — none found. Every code step has full code.

**Type consistency:** `Event(kind, source_trader, market_id, side, price, timestamp)` used identically in Task 6 (emit) and Task 8 (consume). `Position` and `TradeRow` dataclasses defined in Task 3, used unchanged in Tasks 8 and 10. `TopTrader` defined in Task 3, returned by Task 5, consumed by Task 9. `LeaderboardEntry`/`Trade` defined in Task 4, used by Tasks 5/6/10.

No gaps found.

---

## Execution Handoff

**Plan complete and saved to `polymarket/docs/superpowers/plans/2026-05-18-polymarket-copy-bot.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
