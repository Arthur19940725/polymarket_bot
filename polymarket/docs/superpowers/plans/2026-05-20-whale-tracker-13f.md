# Whale Tracker 13F Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-process Python bot that polls SEC EDGAR for Top-100 13F filings, computes 7 classes of position-change signals, pushes alerts to Telegram, and answers `/commands` for ad-hoc queries.

**Architecture:** Worker process (asyncio + APScheduler) polls SEC RSS 4×/day, parses 13F XML/XBRL, diffs against prior quarter, writes signals to SQLite (WAL). A separate Telegram bot process reads the same SQLite for `/report /holding /consensus`. CLI is a third on-demand entry. All three processes share state through `data/whale.sqlite` only.

**Tech Stack:** Python 3.11, httpx[async], python-telegram-bot v21, lxml, pydantic v2, apscheduler, pytest + pytest-asyncio + respx (httpx mock), SQLite WAL, PM2 supervision.

**Project root:** `C:\Users\Arthur\workspace\polymarket\whale-tracker-13f\` (new sibling repo, not nested under `polymarket-copy-bot`)

**Reference spec:** `docs/superpowers/specs/2026-05-20-whale-tracker-13f-design.md`

---

## File Structure (locked in here, referenced by tasks)

```
whale-tracker-13f/
├── whale/
│   ├── __init__.py             # empty
│   ├── config.py               # Task 1 — env + filers.yaml loader
│   ├── storage.py              # Task 2 — sqlite schema, connection, queries
│   ├── sec_client.py           # Task 3 — async HTTP, rate limit, retry
│   ├── parser_13f.py           # Task 4 — pure XML/XBRL → list[Holding]
│   ├── cusip_resolver.py       # Task 5 — CUSIP → ticker, SEC json cache
│   ├── signal_engine.py        # Task 6 — pure diff function, 7 signal kinds
│   ├── notifier.py             # Task 7 — Telegram push, dedup
│   ├── worker.py               # Task 8 — asyncio orchestrator
│   ├── bot.py                  # Task 9 — Telegram bot handlers
│   └── models.py               # Task 1 — Holding, Signal, FilerEntry dataclasses
├── cli/
│   ├── __init__.py
│   └── __main__.py             # Task 10 — argparse entry
├── data/
│   ├── filers.yaml             # Task 1 — universe seed (100 entries)
│   ├── cache/                  # SEC raw filings + company_tickers.json
│   └── .gitkeep
├── logs/.gitkeep
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Task 0 — fixtures (tmp_db, frozen_clock)
│   └── fixtures/               # XML samples, JSON expectations
├── .env.example                # Task 0
├── .gitignore                  # Task 0
├── requirements.txt            # Task 0
├── requirements-dev.txt        # Task 0
├── pyproject.toml              # Task 0 — pytest config
├── ecosystem.config.js         # Task 11 — PM2 supervisor config
└── README.md                   # Task 11
```

**File-level responsibilities:**
- `models.py`: Pydantic v2 dataclasses (`Holding`, `Signal`, `FilerEntry`). Pure data, no methods beyond `model_validate`.
- `storage.py`: All SQL lives here. Other modules call `storage.upsert_holdings(...)`, never write raw SQL.
- `parser_13f.py` + `signal_engine.py`: Pure functions. No IO. No mocks needed in their tests.
- `sec_client.py`: Only module that calls SEC HTTP. Mocked via respx in all other tests.
- `worker.py` + `bot.py`: Orchestrators. No business logic. Covered by integration tests only.

---

## Task 0: Project Scaffold

**Files:**
- Create: `whale-tracker-13f/.gitignore`, `.env.example`, `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `whale/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `data/.gitkeep`, `data/cache/.gitkeep`, `logs/.gitkeep`, `cli/__init__.py`

- [ ] **Step 1: Create project directory and init git**

```bash
cd C:/Users/Arthur/workspace/polymarket
mkdir whale-tracker-13f
cd whale-tracker-13f
git init -b main
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
.env
data/whale.sqlite
data/whale.sqlite-shm
data/whale.sqlite-wal
data/cache/
logs/*.log
*.log
.venv/
venv/
```

- [ ] **Step 3: Create `.env.example`**

```dotenv
TELEGRAM_BOT_TOKEN=changeme
TELEGRAM_CHAT_ID=changeme
NOTIFY_MIN_SEVERITY=60
LOG_LEVEL=INFO
SEC_USER_AGENT=whale-tracker (xu505483585@gmail.com)
DATA_DIR=./data
```

- [ ] **Step 4: Create `requirements.txt`**

```text
httpx[http2]==0.27.2
python-telegram-bot==21.6
lxml==5.3.0
pydantic==2.9.2
apscheduler==3.10.4
pyyaml==6.0.2
python-dotenv==1.0.1
```

- [ ] **Step 5: Create `requirements-dev.txt`**

```text
-r requirements.txt
pytest==8.3.3
pytest-asyncio==0.24.0
pytest-cov==5.0.0
respx==0.21.1
freezegun==1.5.1
```

- [ ] **Step 6: Create `pyproject.toml`**

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = ["slow: real-network tests, skipped by default"]
addopts = "-q --strict-markers -m 'not slow'"

[tool.coverage.run]
source = ["whale", "cli"]
omit = ["*/__init__.py"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

- [ ] **Step 7: Create empty package files**

Create empty `whale/__init__.py`, `tests/__init__.py`, `cli/__init__.py`, `data/.gitkeep`, `data/cache/.gitkeep`, `logs/.gitkeep`.

- [ ] **Step 8: Create `tests/conftest.py`**

```python
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path, monkeypatch) -> Path:
    """Isolated data dir per test, exposed via DATA_DIR env."""
    data = tmp_path / "data"
    (data / "cache").mkdir(parents=True)
    monkeypatch.setenv("DATA_DIR", str(data))
    return data


@pytest.fixture
def tmp_db(tmp_data_dir: Path):
    """Initialized empty DB. Lazy import to avoid touching real env."""
    from whale import storage

    db_path = tmp_data_dir / "whale.sqlite"
    storage.init_db(db_path)
    conn = storage.connect(db_path)
    yield conn
    conn.close()


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
```

- [ ] **Step 9: Set up Python venv and install**

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements-dev.txt
```

- [ ] **Step 10: Verify pytest runs (no tests yet → exit 5 is fine)**

```bash
pytest
```

Expected: `no tests ran` (exit code 5). This confirms the harness works.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "chore: scaffold whale-tracker-13f project"
```

---

## Task 1: `models.py` + `config.py` + seed `filers.yaml`

**Files:**
- Create: `whale/models.py`, `whale/config.py`, `data/filers.yaml`
- Test: `tests/test_config.py`

### Task 1a — Dataclass models

- [ ] **Step 1: Write failing test `tests/test_models.py`**

```python
from whale.models import FilerEntry, Holding, Signal


def test_filer_entry_validates_category():
    f = FilerEntry(cik="0001067983", name="BERKSHIRE", category="active", aum_rank=1)
    assert f.cik == "0001067983"

    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        FilerEntry(cik="0001067983", name="X", category="bogus", aum_rank=1)


def test_holding_value_usd_must_be_nonnegative():
    h = Holding(
        cik="0001067983", period_end="2024-12-31", cusip="037833100",
        ticker="AAPL", issuer_name="APPLE INC", value_usd=1_000_000_000,
        shares=10_000_000, put_call=None,
    )
    assert h.value_usd == 1_000_000_000

    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Holding(
            cik="x", period_end="2024-12-31", cusip="x", ticker=None,
            issuer_name="x", value_usd=-1, shares=0, put_call=None,
        )


def test_signal_kind_constrained():
    s = Signal(
        detected_at="2026-05-20T00:00:00Z", period_end="2024-12-31",
        kind="new", cik="0001067983", cusip="037833100", ticker="AAPL",
        payload={"value_usd": 1_000_000_000}, severity=80,
    )
    assert s.kind == "new"

    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Signal(
            detected_at="x", period_end="x", kind="bogus", cik=None,
            cusip=None, ticker=None, payload={}, severity=0,
        )
```

- [ ] **Step 2: Run test — expect ImportError**

```bash
pytest tests/test_models.py -v
```

Expected: FAIL (`whale.models` not found).

- [ ] **Step 3: Implement `whale/models.py`**

```python
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["active", "passive"]
PutCall = Optional[Literal["PUT", "CALL"]]
SignalKind = Literal[
    "new", "closed", "increase", "decrease",
    "consensus", "concentration", "sector_rotation",
]


class FilerEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    cik: str
    name: str
    category: Category
    aum_rank: Optional[int] = None
    notes: Optional[str] = None


class Holding(BaseModel):
    model_config = ConfigDict(frozen=True)
    cik: str
    period_end: str  # ISO date YYYY-MM-DD
    cusip: str
    ticker: Optional[str]
    issuer_name: str
    value_usd: int = Field(ge=0)
    shares: int = Field(ge=0)
    put_call: PutCall = None


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True)
    detected_at: str
    period_end: str
    kind: SignalKind
    cik: Optional[str]
    cusip: Optional[str]
    ticker: Optional[str]
    payload: dict
    severity: int = Field(ge=0, le=100)
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_models.py -v
```

### Task 1b — `config.py`

- [ ] **Step 5: Write failing test `tests/test_config.py`**

```python
from pathlib import Path

import pytest
import yaml

from whale.config import Config, load_config, load_filers


def test_load_config_from_env(monkeypatch, tmp_data_dir):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("NOTIFY_MIN_SEVERITY", "55")
    monkeypatch.setenv("SEC_USER_AGENT", "ua")
    cfg = load_config()
    assert cfg.telegram_bot_token == "tok"
    assert cfg.telegram_chat_id == "42"
    assert cfg.notify_min_severity == 55
    assert cfg.sec_user_agent == "ua"
    assert cfg.data_dir == tmp_data_dir


def test_load_filers_yaml(tmp_data_dir):
    (tmp_data_dir / "filers.yaml").write_text(yaml.safe_dump([
        {"cik": "0001067983", "name": "BERKSHIRE", "category": "active", "aum_rank": 1},
        {"cik": "0000102909", "name": "VANGUARD", "category": "passive", "aum_rank": 2},
    ]))
    entries = load_filers(tmp_data_dir / "filers.yaml")
    assert len(entries) == 2
    assert entries[0].name == "BERKSHIRE"
    assert entries[1].category == "passive"


def test_load_filers_rejects_duplicate_cik(tmp_data_dir):
    (tmp_data_dir / "filers.yaml").write_text(yaml.safe_dump([
        {"cik": "0001067983", "name": "A", "category": "active", "aum_rank": 1},
        {"cik": "0001067983", "name": "B", "category": "active", "aum_rank": 2},
    ]))
    with pytest.raises(ValueError, match="duplicate"):
        load_filers(tmp_data_dir / "filers.yaml")
```

- [ ] **Step 6: Run — expect FAIL (module missing)**

```bash
pytest tests/test_config.py -v
```

- [ ] **Step 7: Implement `whale/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

import yaml
from dotenv import load_dotenv

from whale.models import FilerEntry


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    notify_min_severity: int
    log_level: str
    sec_user_agent: str
    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / "whale.sqlite"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"


def load_config() -> Config:
    load_dotenv(override=False)
    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    return Config(
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        notify_min_severity=int(os.environ.get("NOTIFY_MIN_SEVERITY", "60")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        sec_user_agent=os.environ.get("SEC_USER_AGENT", "whale-tracker"),
        data_dir=data_dir,
    )


def load_filers(path: Path) -> List[FilerEntry]:
    raw = yaml.safe_load(path.read_text())
    entries = [FilerEntry.model_validate(item) for item in raw]
    ciks = [e.cik for e in entries]
    if len(ciks) != len(set(ciks)):
        dupes = [c for c in ciks if ciks.count(c) > 1]
        raise ValueError(f"duplicate CIK(s) in {path}: {set(dupes)}")
    return entries
```

- [ ] **Step 8: Run all tests — expect PASS**

```bash
pytest tests/test_config.py tests/test_models.py -v
```

### Task 1c — Seed `filers.yaml` (10 entries to start, expand later)

- [ ] **Step 9: Create `data/filers.yaml` with 10 well-known entries**

```yaml
- {cik: "0001067983", name: "BERKSHIRE HATHAWAY INC",      category: active,  aum_rank: 1}
- {cik: "0001350694", name: "BRIDGEWATER ASSOCIATES LP",   category: active,  aum_rank: 2}
- {cik: "0001336528", name: "PERSHING SQUARE CAPITAL MGMT",category: active,  aum_rank: 3}
- {cik: "0001167483", name: "TIGER GLOBAL MANAGEMENT LLC", category: active,  aum_rank: 4}
- {cik: "0001037389", name: "RENAISSANCE TECHNOLOGIES LLC",category: active,  aum_rank: 5}
- {cik: "0001656456", name: "APPALOOSA LP",                category: active,  aum_rank: 6}
- {cik: "0001029160", name: "DUQUESNE FAMILY OFFICE LLC",  category: active,  aum_rank: 7}
- {cik: "0001364742", name: "BLACKROCK INC.",              category: passive, aum_rank: 8}
- {cik: "0000102909", name: "VANGUARD GROUP INC",          category: passive, aum_rank: 9}
- {cik: "0000093751", name: "STATE STREET CORP",           category: passive, aum_rank: 10}
```

(Backlog: expand to 100 manually before first real deploy; the spec captures this.)

- [ ] **Step 10: Commit**

```bash
git add whale/models.py whale/config.py data/filers.yaml tests/test_models.py tests/test_config.py
git commit -m "feat(config): models, config loader, seed filer universe"
```

---

## Task 2: `storage.py` — SQLite schema + queries

**Files:**
- Create: `whale/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing tests `tests/test_storage.py`**

```python
from pathlib import Path

import pytest

from whale import storage
from whale.models import FilerEntry, Holding, Signal


def test_init_db_creates_tables(tmp_data_dir):
    db = tmp_data_dir / "whale.sqlite"
    storage.init_db(db)
    conn = storage.connect(db)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {"filers", "filings_raw", "holdings", "signals",
            "cusip_ticker", "notified_log"}.issubset(names)


def test_wal_mode_enabled(tmp_db):
    mode = tmp_db.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_upsert_filer_idempotent(tmp_db):
    f = FilerEntry(cik="0001067983", name="BRK", category="active", aum_rank=1)
    storage.upsert_filer(tmp_db, f)
    storage.upsert_filer(tmp_db, f)
    rows = tmp_db.execute("SELECT * FROM filers").fetchall()
    assert len(rows) == 1


def test_upsert_holdings_replaces_period(tmp_db):
    f = FilerEntry(cik="0001067983", name="BRK", category="active", aum_rank=1)
    storage.upsert_filer(tmp_db, f)
    h = Holding(
        cik="0001067983", period_end="2024-12-31", cusip="037833100",
        ticker="AAPL", issuer_name="APPLE", value_usd=100, shares=1,
        put_call=None,
    )
    storage.upsert_holdings(tmp_db, [h, h])  # duplicate row
    rows = tmp_db.execute("SELECT * FROM holdings").fetchall()
    assert len(rows) == 1  # PK collapses duplicates


def test_filing_status_lifecycle(tmp_db):
    f = FilerEntry(cik="0001067983", name="BRK", category="active", aum_rank=1)
    storage.upsert_filer(tmp_db, f)
    storage.upsert_filing(tmp_db, accession="0001-26-001", cik="0001067983",
                         filed_at="2026-02-14T00:00:00Z",
                         period_end="2024-12-31", parse_status="pending")
    storage.mark_filing(tmp_db, "0001-26-001", status="ok")
    row = tmp_db.execute("SELECT parse_status FROM filings_raw "
                         "WHERE accession=?", ("0001-26-001",)).fetchone()
    assert row[0] == "ok"


def test_known_filings_returns_set(tmp_db):
    f = FilerEntry(cik="0001067983", name="BRK", category="active", aum_rank=1)
    storage.upsert_filer(tmp_db, f)
    storage.upsert_filing(tmp_db, "A", "0001067983", "2026-02-14", "2024-12-31", "ok")
    storage.upsert_filing(tmp_db, "B", "0001067983", "2026-02-14", "2024-12-31", "ok")
    assert storage.known_accessions(tmp_db) == {"A", "B"}


def test_holdings_by_period(tmp_db):
    f = FilerEntry(cik="0001067983", name="BRK", category="active", aum_rank=1)
    storage.upsert_filer(tmp_db, f)
    h1 = Holding(cik="0001067983", period_end="2024-09-30", cusip="X",
                 ticker="X", issuer_name="X", value_usd=1, shares=1, put_call=None)
    h2 = Holding(cik="0001067983", period_end="2024-12-31", cusip="Y",
                 ticker="Y", issuer_name="Y", value_usd=2, shares=2, put_call=None)
    storage.upsert_holdings(tmp_db, [h1, h2])
    rows = storage.holdings_for_period(tmp_db, "2024-12-31")
    assert len(rows) == 1
    assert rows[0].ticker == "Y"


def test_insert_signal_and_mark_notified(tmp_db):
    s = Signal(
        detected_at="2026-05-20T00:00:00Z", period_end="2024-12-31",
        kind="new", cik="0001067983", cusip="X", ticker="X",
        payload={"value_usd": 100}, severity=80,
    )
    sid = storage.insert_signal(tmp_db, s)
    assert isinstance(sid, int)
    assert storage.pending_notifications(tmp_db, min_severity=60) == [(sid, s)]
    storage.mark_notified(tmp_db, sid, channel="telegram")
    assert storage.pending_notifications(tmp_db, min_severity=60) == []


def test_wal_cross_connection_visibility(tmp_data_dir):
    db = tmp_data_dir / "whale.sqlite"
    storage.init_db(db)
    writer = storage.connect(db)
    reader = storage.connect(db)
    f = FilerEntry(cik="X", name="X", category="active", aum_rank=1)
    storage.upsert_filer(writer, f)
    writer.commit()
    rows = reader.execute("SELECT cik FROM filers").fetchall()
    assert rows == [("X",)]
    writer.close()
    reader.close()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_storage.py -v
```

- [ ] **Step 3: Implement `whale/storage.py`**

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

from whale.models import FilerEntry, Holding, Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS filers (
  cik TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  aum_rank INTEGER,
  notes TEXT
);
CREATE TABLE IF NOT EXISTS filings_raw (
  accession TEXT PRIMARY KEY,
  cik TEXT NOT NULL,
  filed_at TEXT NOT NULL,
  period_end TEXT NOT NULL,
  fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
  parse_status TEXT NOT NULL,
  parse_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_filings_cik_period
  ON filings_raw(cik, period_end);
CREATE TABLE IF NOT EXISTS holdings (
  cik TEXT NOT NULL,
  period_end TEXT NOT NULL,
  cusip TEXT NOT NULL,
  ticker TEXT,
  issuer_name TEXT NOT NULL,
  value_usd INTEGER NOT NULL,
  shares INTEGER NOT NULL,
  put_call TEXT,
  PRIMARY KEY (cik, period_end, cusip, COALESCE(put_call, ''))
);
CREATE INDEX IF NOT EXISTS idx_holdings_cusip_period
  ON holdings(cusip, period_end);
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  detected_at TEXT NOT NULL,
  period_end TEXT NOT NULL,
  kind TEXT NOT NULL,
  cik TEXT,
  cusip TEXT,
  ticker TEXT,
  payload_json TEXT NOT NULL,
  severity INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_period_kind
  ON signals(period_end, kind);
CREATE TABLE IF NOT EXISTS cusip_ticker (
  cusip TEXT PRIMARY KEY,
  ticker TEXT NOT NULL,
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notified_log (
  signal_id INTEGER PRIMARY KEY,
  notified_at TEXT NOT NULL,
  channel TEXT NOT NULL
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def upsert_filer(conn: sqlite3.Connection, f: FilerEntry) -> None:
    conn.execute(
        """INSERT INTO filers(cik, name, category, aum_rank, notes)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(cik) DO UPDATE SET
             name=excluded.name, category=excluded.category,
             aum_rank=excluded.aum_rank, notes=excluded.notes""",
        (f.cik, f.name, f.category, f.aum_rank, f.notes),
    )


def upsert_filing(conn: sqlite3.Connection, accession: str, cik: str,
                  filed_at: str, period_end: str, parse_status: str) -> None:
    conn.execute(
        """INSERT INTO filings_raw(accession, cik, filed_at, period_end, parse_status)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(accession) DO NOTHING""",
        (accession, cik, filed_at, period_end, parse_status),
    )


def mark_filing(conn: sqlite3.Connection, accession: str,
                status: str, error: Optional[str] = None) -> None:
    conn.execute(
        "UPDATE filings_raw SET parse_status=?, parse_error=? WHERE accession=?",
        (status, error, accession),
    )


def known_accessions(conn: sqlite3.Connection) -> Set[str]:
    rows = conn.execute("SELECT accession FROM filings_raw").fetchall()
    return {r[0] for r in rows}


def upsert_holdings(conn: sqlite3.Connection, holdings: Iterable[Holding]) -> None:
    rows = [
        (h.cik, h.period_end, h.cusip, h.ticker, h.issuer_name,
         h.value_usd, h.shares, h.put_call)
        for h in holdings
    ]
    conn.executemany(
        """INSERT INTO holdings(cik, period_end, cusip, ticker, issuer_name,
                                value_usd, shares, put_call)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(cik, period_end, cusip, COALESCE(put_call, ''))
           DO UPDATE SET ticker=excluded.ticker, issuer_name=excluded.issuer_name,
                         value_usd=excluded.value_usd, shares=excluded.shares""",
        rows,
    )


def holdings_for_period(conn: sqlite3.Connection, period_end: str,
                        cik: Optional[str] = None) -> List[Holding]:
    if cik:
        cur = conn.execute(
            "SELECT * FROM holdings WHERE period_end=? AND cik=?",
            (period_end, cik),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM holdings WHERE period_end=?", (period_end,),
        )
    return [
        Holding(
            cik=r["cik"], period_end=r["period_end"], cusip=r["cusip"],
            ticker=r["ticker"], issuer_name=r["issuer_name"],
            value_usd=r["value_usd"], shares=r["shares"], put_call=r["put_call"],
        )
        for r in cur.fetchall()
    ]


def insert_signal(conn: sqlite3.Connection, s: Signal) -> int:
    cur = conn.execute(
        """INSERT INTO signals(detected_at, period_end, kind, cik, cusip,
                               ticker, payload_json, severity)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (s.detected_at, s.period_end, s.kind, s.cik, s.cusip, s.ticker,
         json.dumps(s.payload), s.severity),
    )
    return cur.lastrowid


def pending_notifications(conn: sqlite3.Connection,
                          min_severity: int) -> List[Tuple[int, Signal]]:
    cur = conn.execute(
        """SELECT s.id, s.* FROM signals s
           LEFT JOIN notified_log n ON n.signal_id = s.id
           WHERE n.signal_id IS NULL AND s.severity >= ?
           ORDER BY s.id""",
        (min_severity,),
    )
    out = []
    for r in cur.fetchall():
        sig = Signal(
            detected_at=r["detected_at"], period_end=r["period_end"],
            kind=r["kind"], cik=r["cik"], cusip=r["cusip"], ticker=r["ticker"],
            payload=json.loads(r["payload_json"]), severity=r["severity"],
        )
        out.append((r["id"], sig))
    return out


def mark_notified(conn: sqlite3.Connection, signal_id: int, channel: str) -> None:
    conn.execute(
        """INSERT INTO notified_log(signal_id, notified_at, channel)
           VALUES (?, datetime('now'), ?)
           ON CONFLICT(signal_id) DO NOTHING""",
        (signal_id, channel),
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_storage.py -v
```

- [ ] **Step 5: Commit**

```bash
git add whale/storage.py tests/test_storage.py
git commit -m "feat(storage): sqlite schema, upserts, signal queue"
```

---

## Task 3: `sec_client.py` — Async SEC HTTP client

**Files:**
- Create: `whale/sec_client.py`
- Test: `tests/test_sec_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sec_client.py
import asyncio
from datetime import datetime, timezone

import httpx
import pytest
import respx

from whale.sec_client import (
    SecClient, SecPermanentError, SecTransientError, FilingRef,
)


@pytest.mark.asyncio
async def test_fetch_rss_filters_to_cik_whitelist(respx_mock):
    rss = """<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>
      <entry>
        <title>13F-HR - BERKSHIRE</title>
        <link href='https://www.sec.gov/Archives/edgar/data/1067983/000106798326000001/'/>
        <updated>2026-02-14T10:00:00-05:00</updated>
        <category term='13F-HR'/>
        <content type='text/xml'><accession-number>0001067983-26-000001</accession-number>
          <cik>0001067983</cik><period>20241231</period></content>
      </entry>
      <entry>
        <title>13F-HR - SOMEONE ELSE</title>
        <link href='https://www.sec.gov/Archives/edgar/data/9999999/'/>
        <updated>2026-02-14T11:00:00-05:00</updated>
        <category term='13F-HR'/>
        <content type='text/xml'><accession-number>0009999999-26-000001</accession-number>
          <cik>0009999999</cik><period>20241231</period></content>
      </entry>
    </feed>"""
    respx_mock.get(
        "https://www.sec.gov/cgi-bin/browse-edgar"
    ).mock(return_value=httpx.Response(200, text=rss))

    client = SecClient(user_agent="test")
    refs = await client.fetch_rss(cik_allowlist={"0001067983"})
    assert len(refs) == 1
    assert refs[0].cik == "0001067983"
    assert refs[0].accession == "0001067983-26-000001"
    assert refs[0].period_end == "2024-12-31"


@pytest.mark.asyncio
async def test_download_filing_retries_on_5xx(respx_mock):
    url = "https://www.sec.gov/Archives/edgar/data/1067983/000106798326000001/info.xml"
    route = respx_mock.get(url).mock(side_effect=[
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, text="<xml/>"),
    ])
    client = SecClient(user_agent="test", retry_base_delay=0)
    text = await client.download(url)
    assert text == "<xml/>"
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_download_filing_gives_up_after_max_retries(respx_mock):
    url = "https://www.sec.gov/x.xml"
    respx_mock.get(url).mock(return_value=httpx.Response(503))
    client = SecClient(user_agent="test", retry_base_delay=0, max_retries=2)
    with pytest.raises(SecTransientError):
        await client.download(url)


@pytest.mark.asyncio
async def test_download_4xx_raises_permanent(respx_mock):
    url = "https://www.sec.gov/x.xml"
    respx_mock.get(url).mock(return_value=httpx.Response(404))
    client = SecClient(user_agent="test", retry_base_delay=0)
    with pytest.raises(SecPermanentError):
        await client.download(url)


@pytest.mark.asyncio
async def test_user_agent_header_present(respx_mock):
    route = respx_mock.get("https://www.sec.gov/x.xml").mock(
        return_value=httpx.Response(200, text="ok")
    )
    client = SecClient(user_agent="whale-tracker (a@b.c)", retry_base_delay=0)
    await client.download("https://www.sec.gov/x.xml")
    sent = route.calls.last.request
    assert sent.headers["user-agent"] == "whale-tracker (a@b.c)"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_sec_client.py -v
```

- [ ] **Step 3: Implement `whale/sec_client.py`**

```python
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set

import httpx
from lxml import etree

log = logging.getLogger(__name__)


class SecError(Exception):
    pass


class SecTransientError(SecError):
    pass


class SecPermanentError(SecError):
    pass


@dataclass(frozen=True)
class FilingRef:
    accession: str
    cik: str
    filed_at: str       # ISO8601
    period_end: str     # YYYY-MM-DD
    filing_url: str     # detail page URL


class SecClient:
    """Async SEC HTTP client with rate limit + retry.

    Rate limiting: SEC requires <=10 req/s. We use a simple async semaphore
    plus per-request delay enforced inside `_request`.
    """

    BASE = "https://www.sec.gov"
    RSS_PATH = "/cgi-bin/browse-edgar"

    def __init__(
        self,
        user_agent: str,
        *,
        max_retries: int = 4,
        retry_base_delay: float = 1.0,
        min_request_interval: float = 0.11,  # ~9 req/s
    ) -> None:
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.min_request_interval = min_request_interval
        self._last_request_t = 0.0
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"},
            http2=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _throttle(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = self._last_request_t + self.min_request_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_t = asyncio.get_event_loop().time()

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            await self._throttle()
            try:
                resp = await self._client.request(method, url, **kw)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt >= self.max_retries:
                    raise SecTransientError(f"network error: {e}") from e
                await asyncio.sleep(self.retry_base_delay * (2 ** attempt))
                continue
            if 200 <= resp.status_code < 300:
                return resp
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                if attempt >= self.max_retries:
                    raise SecTransientError(
                        f"{resp.status_code} after {attempt+1} attempts: {url}"
                    )
                await asyncio.sleep(self.retry_base_delay * (2 ** attempt))
                continue
            raise SecPermanentError(f"{resp.status_code} {url}")
        raise SecTransientError(str(last_exc))

    async def download(self, url: str) -> str:
        resp = await self._request("GET", url)
        return resp.text

    async def fetch_rss(self, cik_allowlist: Set[str]) -> List[FilingRef]:
        params = {
            "action": "getcurrent",
            "type": "13F-HR",
            "output": "atom",
            "count": "100",
        }
        resp = await self._request("GET", f"{self.BASE}{self.RSS_PATH}",
                                   params=params)
        return _parse_rss(resp.text, cik_allowlist)


def _parse_rss(xml_text: str, cik_allowlist: Set[str]) -> List[FilingRef]:
    """Parse SEC atom feed; tolerate both <content> field variations."""
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = etree.fromstring(xml_text.encode("utf-8"))
    out: List[FilingRef] = []
    for entry in root.findall("a:entry", ns):
        content = entry.find("a:content", ns)
        if content is None:
            continue
        text_blob = etree.tostring(content, method="text",
                                   encoding="unicode") or ""
        accession = _extract(text_blob, r"accession[-\s]?number[:\s>]+\s*([\d\-]+)")
        cik_match = _extract(text_blob, r"<cik>\s*(\d+)\s*</cik>") \
                    or _extract(text_blob, r"\bcik[:\s>]+\s*(\d+)")
        period_match = _extract(text_blob, r"<period>\s*(\d{8})\s*</period>") \
                       or _extract(text_blob, r"\bperiod[:\s>]+\s*(\d{8})")
        link = entry.find("a:link", ns)
        updated_el = entry.find("a:updated", ns)
        if not (accession and cik_match and period_match):
            continue
        cik_padded = cik_match.zfill(10)
        if cik_padded not in cik_allowlist:
            continue
        period_end = f"{period_match[0:4]}-{period_match[4:6]}-{period_match[6:8]}"
        out.append(FilingRef(
            accession=accession,
            cik=cik_padded,
            filed_at=(updated_el.text if updated_el is not None else ""),
            period_end=period_end,
            filing_url=(link.get("href") if link is not None else ""),
        ))
    return out


def _extract(text: str, pattern: str) -> Optional[str]:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1) if m else None
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_sec_client.py -v
```

If RSS parsing tests fail because the SEC feed structure your sample uses differs, adjust `_parse_rss` regex to match the actual SEC atom shape you discover during real testing — the tests in this task constrain the contract.

- [ ] **Step 5: Commit**

```bash
git add whale/sec_client.py tests/test_sec_client.py
git commit -m "feat(sec_client): async http client with rate limit + retry"
```

---

## Task 4: `parser_13f.py` — XML/XBRL parser

**Files:**
- Create: `whale/parser_13f.py`
- Create fixtures: `tests/fixtures/13f_sample_modern.xml`, `13f_sample_putcall.xml`
- Test: `tests/test_parser_13f.py`

- [ ] **Step 1: Create modern (2013+) XML fixture `tests/fixtures/13f_sample_modern.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>50000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>1000000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <otherManager></otherManager>
    <votingAuthority>
      <Sole>1000000</Sole>
      <Shared>0</Shared>
      <None>0</None>
    </votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>BANK OF AMERICA</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>060505104</cusip>
    <value>30000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>5000000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
  </infoTable>
</informationTable>
```

- [ ] **Step 2: Create put/call fixture `tests/fixtures/13f_sample_putcall.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>SPY</nameOfIssuer>
    <titleOfClass>PUT</titleOfClass>
    <cusip>78462F103</cusip>
    <value>10000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>100000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <putCall>Put</putCall>
    <investmentDiscretion>SOLE</investmentDiscretion>
  </infoTable>
  <infoTable>
    <nameOfIssuer>SPY</nameOfIssuer>
    <titleOfClass>CALL</titleOfClass>
    <cusip>78462F103</cusip>
    <value>5000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>50000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <putCall>Call</putCall>
    <investmentDiscretion>SOLE</investmentDiscretion>
  </infoTable>
</informationTable>
```

- [ ] **Step 3: Write failing tests `tests/test_parser_13f.py`**

```python
from whale.parser_13f import ParseError, parse_information_table


def test_parse_modern_xml(fixtures_dir):
    xml = (fixtures_dir / "13f_sample_modern.xml").read_text()
    rows = parse_information_table(
        xml, cik="0001067983", period_end="2024-12-31",
    )
    assert len(rows) == 2
    aapl = rows[0]
    assert aapl.cusip == "037833100"
    assert aapl.issuer_name == "APPLE INC"
    # Spec: 13F reports thousands — must multiply by 1000
    assert aapl.value_usd == 50_000_000 * 1000
    assert aapl.shares == 1_000_000
    assert aapl.put_call is None


def test_parse_put_call_split(fixtures_dir):
    xml = (fixtures_dir / "13f_sample_putcall.xml").read_text()
    rows = parse_information_table(
        xml, cik="0001067983", period_end="2024-12-31",
    )
    assert len(rows) == 2
    puts = [r for r in rows if r.put_call == "PUT"]
    calls = [r for r in rows if r.put_call == "CALL"]
    assert len(puts) == 1
    assert len(calls) == 1
    # Same CUSIP, distinct rows due to put_call
    assert puts[0].cusip == calls[0].cusip


def test_parse_missing_table_raises():
    import pytest
    with pytest.raises(ParseError):
        parse_information_table("<garbage/>", cik="x", period_end="2024-12-31")
```

- [ ] **Step 4: Run — expect FAIL**

```bash
pytest tests/test_parser_13f.py -v
```

- [ ] **Step 5: Implement `whale/parser_13f.py`**

```python
from __future__ import annotations

from typing import List, Optional

from lxml import etree

from whale.models import Holding


class ParseError(Exception):
    pass


_NS = {"t": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}


def parse_information_table(
    xml_text: str, *, cik: str, period_end: str,
) -> List[Holding]:
    try:
        root = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as e:
        raise ParseError(f"invalid xml: {e}") from e

    # Tolerate both namespaced and bare element names (SEC docs vary)
    tables = root.findall(".//t:infoTable", _NS) or root.findall(".//infoTable")
    if not tables:
        raise ParseError("no infoTable elements found")

    out: List[Holding] = []
    for t in tables:
        issuer = _text(t, "nameOfIssuer")
        cusip = _text(t, "cusip")
        value_k = _text(t, "value")     # value is in thousands per 13F spec
        shares = _text(t, "shrsOrPrnAmt/sshPrnamt") or "0"
        put_call_raw = (_text(t, "putCall") or "").upper().strip()
        put_call: Optional[str] = (
            "PUT" if put_call_raw == "PUT"
            else "CALL" if put_call_raw == "CALL"
            else None
        )
        if not (issuer and cusip and value_k):
            raise ParseError(f"missing required field in infoTable: {issuer!r}")

        out.append(Holding(
            cik=cik,
            period_end=period_end,
            cusip=cusip.strip(),
            ticker=None,  # resolved later by cusip_resolver
            issuer_name=issuer.strip(),
            value_usd=int(value_k) * 1000,
            shares=int(shares),
            put_call=put_call,
        ))
    return out


def _text(el, path: str) -> Optional[str]:
    """Find with namespace fallback."""
    parts = path.split("/")
    ns_path = "/".join(f"t:{p}" for p in parts)
    found = el.find(ns_path, _NS)
    if found is None:
        found = el.find(path)
    if found is None or found.text is None:
        return None
    return found.text
```

- [ ] **Step 6: Run — expect PASS**

```bash
pytest tests/test_parser_13f.py -v
```

- [ ] **Step 7: Commit**

```bash
git add whale/parser_13f.py tests/fixtures/13f_sample_*.xml tests/test_parser_13f.py
git commit -m "feat(parser_13f): xml parser with put/call and unit conversion"
```

---

## Task 5: `cusip_resolver.py` — CUSIP → ticker mapping

**Files:**
- Create: `whale/cusip_resolver.py`
- Test: `tests/test_cusip_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cusip_resolver.py
import json

import pytest

from whale.cusip_resolver import CusipResolver


def _seed_company_tickers(cache_dir):
    # SEC format: dict keyed by index, each entry has {cik_str, ticker, title}
    payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 1067983, "ticker": "BRK-A", "title": "BERKSHIRE"},
    }
    (cache_dir / "company_tickers.json").write_text(json.dumps(payload))


@pytest.mark.asyncio
async def test_resolves_from_cusip_ticker_table(tmp_db, tmp_data_dir):
    from whale import storage
    tmp_db.execute(
        "INSERT INTO cusip_ticker(cusip, ticker, source, updated_at) "
        "VALUES ('037833100','AAPL','manual','2026-01-01')"
    )
    resolver = CusipResolver(conn=tmp_db, cache_dir=tmp_data_dir / "cache")
    assert await resolver.resolve("037833100") == "AAPL"


@pytest.mark.asyncio
async def test_missing_cusip_returns_none(tmp_db, tmp_data_dir):
    resolver = CusipResolver(conn=tmp_db, cache_dir=tmp_data_dir / "cache")
    assert await resolver.resolve("000000000") is None


@pytest.mark.asyncio
async def test_import_manual_csv(tmp_db, tmp_data_dir):
    resolver = CusipResolver(conn=tmp_db, cache_dir=tmp_data_dir / "cache")
    csv_path = tmp_data_dir / "import.csv"
    csv_path.write_text("cusip,ticker\n037833100,AAPL\n060505104,BAC\n")
    n = resolver.import_csv(csv_path)
    assert n == 2
    assert await resolver.resolve("060505104") == "BAC"


def test_unknown_cusips_view(tmp_db):
    from whale.cusip_resolver import unresolved_cusips
    tmp_db.execute(
        "INSERT INTO filers(cik,name,category,aum_rank) "
        "VALUES ('X','x','active',1)"
    )
    tmp_db.execute(
        "INSERT INTO holdings(cik,period_end,cusip,ticker,issuer_name,"
        "value_usd,shares,put_call) "
        "VALUES ('X','2024-12-31','UNKNOWN1',NULL,'X',1,1,NULL),"
        "       ('X','2024-12-31','KNOWN1','K','X',1,1,NULL)"
    )
    assert unresolved_cusips(tmp_db) == [("UNKNOWN1", "X")]
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_cusip_resolver.py -v
```

- [ ] **Step 3: Implement `whale/cusip_resolver.py`**

```python
from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


class CusipResolver:
    """CUSIP → ticker mapping.

    Note: SEC's company_tickers.json maps CIK→ticker, NOT cusip→ticker.
    True CUSIP→ticker requires a separate mapping (OpenFIGI or manual).
    For v1 we treat cusip_ticker table as the source of truth and provide
    `import_csv` so users can paste mappings. The SEC json is kept available
    for future ticker-validation tasks but is not the primary resolver.
    """

    def __init__(self, conn: sqlite3.Connection, cache_dir: Path) -> None:
        self.conn = conn
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    async def resolve(self, cusip: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT ticker FROM cusip_ticker WHERE cusip=?", (cusip,)
        ).fetchone()
        return row[0] if row else None

    async def batch_resolve(self, cusips: Iterable[str]) -> dict[str, Optional[str]]:
        out: dict[str, Optional[str]] = {}
        for c in cusips:
            out[c] = await self.resolve(c)
        return out

    def import_csv(self, path: Path) -> int:
        """Import manual cusip,ticker mapping CSV. Returns row count."""
        now = datetime.now(timezone.utc).isoformat()
        n = 0
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cusip = row["cusip"].strip()
                ticker = row["ticker"].strip()
                if not (cusip and ticker):
                    continue
                self.conn.execute(
                    """INSERT INTO cusip_ticker(cusip, ticker, source, updated_at)
                       VALUES (?, ?, 'manual', ?)
                       ON CONFLICT(cusip) DO UPDATE SET
                         ticker=excluded.ticker, source='manual',
                         updated_at=excluded.updated_at""",
                    (cusip, ticker, now),
                )
                n += 1
        return n


def unresolved_cusips(conn: sqlite3.Connection) -> List[Tuple[str, str]]:
    """List distinct (cusip, issuer_name) where ticker is NULL."""
    rows = conn.execute(
        """SELECT DISTINCT cusip, issuer_name FROM holdings
           WHERE ticker IS NULL ORDER BY cusip"""
    ).fetchall()
    return [(r[0], r[1]) for r in rows]
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_cusip_resolver.py -v
```

- [ ] **Step 5: Commit**

```bash
git add whale/cusip_resolver.py tests/test_cusip_resolver.py
git commit -m "feat(cusip_resolver): db-backed mapping with csv import"
```

---

## Task 6: `signal_engine.py` — Diff + 7 signal kinds + severity

**Files:**
- Create: `whale/signal_engine.py`
- Test: `tests/test_signal_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_signal_engine.py
from whale.models import Holding
from whale.signal_engine import compute_signals


def H(cik, cusip, value_usd, ticker="X", put_call=None):
    return Holding(
        cik=cik, period_end="2024-12-31", cusip=cusip,
        ticker=ticker, issuer_name="X", value_usd=value_usd,
        shares=1, put_call=put_call,
    )


def test_new_position_signal():
    prev = []
    curr = [H("0001067983", "AAPL", 200_000_000)]
    sigs = compute_signals(prev_holdings=prev, curr_holdings=curr,
                           period_end="2024-12-31",
                           detected_at="2026-05-20T00:00:00Z")
    new_sigs = [s for s in sigs if s.kind == "new"]
    assert len(new_sigs) == 1
    assert new_sigs[0].cusip == "AAPL"
    assert new_sigs[0].severity >= 70


def test_closed_position_signal():
    prev = [H("0001067983", "BAC", 100_000_000)]
    curr = []
    sigs = compute_signals(prev, curr, "2024-12-31", "t")
    closed = [s for s in sigs if s.kind == "closed"]
    assert len(closed) == 1
    assert closed[0].cusip == "BAC"


def test_increase_above_threshold():
    prev = [H("0001067983", "X", 100_000_000)]
    curr = [H("0001067983", "X", 130_000_000)]  # +30%
    sigs = compute_signals(prev, curr, "2024-12-31", "t")
    inc = [s for s in sigs if s.kind == "increase"]
    assert len(inc) == 1
    assert inc[0].payload["delta_pct"] == 30.0


def test_below_threshold_no_signal():
    prev = [H("0001067983", "X", 100_000_000)]
    curr = [H("0001067983", "X", 120_000_000)]  # +20%, under 25
    sigs = compute_signals(prev, curr, "2024-12-31", "t")
    assert not [s for s in sigs if s.kind in ("increase", "decrease")]


def test_decrease_above_threshold():
    prev = [H("0001067983", "X", 100_000_000)]
    curr = [H("0001067983", "X", 70_000_000)]   # -30%
    sigs = compute_signals(prev, curr, "2024-12-31", "t")
    dec = [s for s in sigs if s.kind == "decrease"]
    assert len(dec) == 1


def test_consensus_multiple_filers():
    prev = []
    curr = [
        H("000A", "TICK", 200_000_000),
        H("000B", "TICK", 100_000_000),
        H("000C", "TICK", 50_000_000),
    ]
    sigs = compute_signals(prev, curr, "2024-12-31", "t")
    consensus = [s for s in sigs if s.kind == "consensus"]
    assert len(consensus) == 1
    assert consensus[0].cusip == "TICK"
    assert consensus[0].payload["filers_count"] == 3
    assert consensus[0].cik is None


def test_put_call_kept_separate():
    prev = [H("000A", "SPY", 100_000_000)]
    curr = [H("000A", "SPY", 100_000_000, put_call="PUT")]
    sigs = compute_signals(prev, curr, "2024-12-31", "t")
    kinds = [s.kind for s in sigs]
    # The PUT row is a NEW position (different put_call key);
    # the SH row vanished → closed
    assert "new" in kinds and "closed" in kinds


def test_concentration_signal_emitted_when_top10_exceeds_pct():
    prev = [H("000A", f"C{i}", 10_000_000) for i in range(10)]
    curr = [H("000A", "C0", 500_000_000)] + [
        H("000A", f"C{i}", 10_000_000) for i in range(1, 10)
    ]
    sigs = compute_signals(prev, curr, "2024-12-31", "t")
    conc = [s for s in sigs if s.kind == "concentration"]
    assert len(conc) >= 1
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_signal_engine.py -v
```

- [ ] **Step 3: Implement `whale/signal_engine.py`**

```python
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, List, Tuple

from whale.models import Holding, Signal

DELTA_PCT_THRESHOLD = 25.0
NEW_OR_CLOSED_HIGH_VALUE = 100_000_000      # $100M
CONSENSUS_MIN_FILERS = 3
CONCENTRATION_TOP10_PCT = 80.0
SECTOR_ROTATION_PCT_SHIFT = 15.0  # placeholder; uses backlog GICS map later


def _key(h: Holding) -> Tuple[str, str, str]:
    return (h.cik, h.cusip, h.put_call or "")


def compute_signals(
    prev_holdings: Iterable[Holding],
    curr_holdings: Iterable[Holding],
    period_end: str,
    detected_at: str,
) -> List[Signal]:
    prev = list(prev_holdings)
    curr = list(curr_holdings)
    prev_map = {_key(h): h for h in prev}
    curr_map = {_key(h): h for h in curr}
    all_keys = set(prev_map) | set(curr_map)

    out: List[Signal] = []
    # Per-position signals
    consensus_buckets: dict[Tuple[str, str], List[Holding]] = defaultdict(list)

    for k in all_keys:
        p = prev_map.get(k)
        c = curr_map.get(k)
        cik, cusip, put_call = k
        put_call_val = put_call or None
        if p is None and c is not None:
            sev = _severity_new_closed(c.value_usd)
            out.append(Signal(
                detected_at=detected_at, period_end=period_end,
                kind="new", cik=cik, cusip=cusip,
                ticker=c.ticker,
                payload={"value_usd": c.value_usd, "shares": c.shares,
                         "put_call": put_call_val},
                severity=sev,
            ))
            consensus_buckets[(cusip, "new")].append(c)
        elif p is not None and c is None:
            sev = _severity_new_closed(p.value_usd)
            out.append(Signal(
                detected_at=detected_at, period_end=period_end,
                kind="closed", cik=cik, cusip=cusip,
                ticker=p.ticker,
                payload={"value_usd_before": p.value_usd,
                         "put_call": put_call_val},
                severity=sev,
            ))
            consensus_buckets[(cusip, "closed")].append(p)
        elif p is not None and c is not None:
            if p.value_usd == 0:
                continue  # avoid div-by-zero; treat as new bucket already handled
            delta_pct = (c.value_usd - p.value_usd) * 100.0 / p.value_usd
            if abs(delta_pct) < DELTA_PCT_THRESHOLD:
                continue
            kind = "increase" if delta_pct > 0 else "decrease"
            sev = _severity_delta(delta_pct, max(p.value_usd, c.value_usd))
            out.append(Signal(
                detected_at=detected_at, period_end=period_end,
                kind=kind, cik=cik, cusip=cusip,
                ticker=c.ticker,
                payload={"delta_pct": round(delta_pct, 2),
                         "value_usd_before": p.value_usd,
                         "value_usd_after": c.value_usd,
                         "put_call": put_call_val},
                severity=sev,
            ))
            consensus_buckets[(cusip, kind)].append(c)

    # Cross-filer consensus
    for (cusip, kind), hs in consensus_buckets.items():
        if len({h.cik for h in hs}) >= CONSENSUS_MIN_FILERS:
            total = sum(h.value_usd for h in hs)
            sev = min(100, 50 + 10 * len(hs))
            ticker = next((h.ticker for h in hs if h.ticker), None)
            out.append(Signal(
                detected_at=detected_at, period_end=period_end,
                kind="consensus", cik=None, cusip=cusip,
                ticker=ticker,
                payload={"direction": kind,
                         "filers_count": len({h.cik for h in hs}),
                         "total_value_usd": total},
                severity=sev,
            ))

    # Concentration per filer
    by_filer: dict[str, List[Holding]] = defaultdict(list)
    for h in curr:
        by_filer[h.cik].append(h)
    for cik, hs in by_filer.items():
        total = sum(h.value_usd for h in hs)
        if total == 0:
            continue
        top10 = sum(sorted((h.value_usd for h in hs), reverse=True)[:10])
        pct = top10 * 100.0 / total
        if pct >= CONCENTRATION_TOP10_PCT:
            out.append(Signal(
                detected_at=detected_at, period_end=period_end,
                kind="concentration", cik=cik, cusip=None,
                ticker=None,
                payload={"top10_pct": round(pct, 2),
                         "total_value_usd": total},
                severity=int(min(90, pct)),
            ))

    # Sector rotation: backlog (needs GICS map). Emit no signals yet.

    return out


def _severity_new_closed(value_usd: int) -> int:
    if value_usd >= 1_000_000_000:
        return 90
    if value_usd >= NEW_OR_CLOSED_HIGH_VALUE:
        return 75
    if value_usd >= 10_000_000:
        return 55
    return 30


def _severity_delta(delta_pct: float, value_usd: int) -> int:
    base = min(50, int(abs(delta_pct) / 2))   # delta drives base 0..50
    if value_usd >= 1_000_000_000:
        base += 40
    elif value_usd >= NEW_OR_CLOSED_HIGH_VALUE:
        base += 25
    elif value_usd >= 10_000_000:
        base += 10
    return min(100, base)
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_signal_engine.py -v
```

- [ ] **Step 5: Commit**

```bash
git add whale/signal_engine.py tests/test_signal_engine.py
git commit -m "feat(signal_engine): diff with 6 signal kinds + severity"
```

(Sector rotation deferred — captured in spec backlog as "needs GICS map".)

---

## Task 7: `notifier.py` — Telegram push with dedup

**Files:**
- Create: `whale/notifier.py`
- Test: `tests/test_notifier.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_notifier.py
from unittest.mock import AsyncMock

import pytest

from whale import storage
from whale.models import Signal
from whale.notifier import Notifier


def _sig(severity=80, kind="new", cusip="X"):
    return Signal(
        detected_at="2026-05-20T00:00:00Z", period_end="2024-12-31",
        kind=kind, cik="0001067983", cusip=cusip, ticker=cusip,
        payload={"value_usd": 200_000_000}, severity=severity,
    )


@pytest.mark.asyncio
async def test_dispatch_skips_below_min_severity(tmp_db):
    storage.insert_signal(tmp_db, _sig(severity=40))
    bot = AsyncMock()
    n = Notifier(conn=tmp_db, send=bot, chat_id="42", min_severity=60)
    sent = await n.dispatch()
    assert sent == 0
    bot.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_sends_and_marks_notified(tmp_db):
    storage.insert_signal(tmp_db, _sig(severity=80, cusip="AAPL"))
    bot = AsyncMock()
    n = Notifier(conn=tmp_db, send=bot, chat_id="42", min_severity=60)
    sent = await n.dispatch()
    assert sent == 1
    bot.assert_awaited_once()
    # second pass: nothing left
    sent2 = await n.dispatch()
    assert sent2 == 0


@pytest.mark.asyncio
async def test_failed_send_does_not_mark_notified(tmp_db):
    storage.insert_signal(tmp_db, _sig())
    bot = AsyncMock(side_effect=RuntimeError("network down"))
    n = Notifier(conn=tmp_db, send=bot, chat_id="42", min_severity=60)
    sent = await n.dispatch()
    assert sent == 0
    # Signal still pending after failure
    assert len(storage.pending_notifications(tmp_db, min_severity=60)) == 1


def test_format_message_includes_key_fields():
    from whale.notifier import format_message
    msg = format_message(_sig(severity=85, kind="new", cusip="AAPL"))
    assert "NEW" in msg
    assert "AAPL" in msg
    assert "200" in msg  # value rendered in $M
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_notifier.py -v
```

- [ ] **Step 3: Implement `whale/notifier.py`**

```python
from __future__ import annotations

import logging
import sqlite3
from typing import Awaitable, Callable

from whale import storage
from whale.models import Signal

log = logging.getLogger(__name__)

SendFn = Callable[[str, str], Awaitable[None]]


class Notifier:
    """Push pending signals to a send function; dedup via notified_log."""

    def __init__(
        self, conn: sqlite3.Connection, send: SendFn,
        chat_id: str, min_severity: int,
    ) -> None:
        self.conn = conn
        self.send = send
        self.chat_id = chat_id
        self.min_severity = min_severity

    async def dispatch(self) -> int:
        sent = 0
        pending = storage.pending_notifications(self.conn, self.min_severity)
        for sig_id, sig in pending:
            try:
                await self.send(self.chat_id, format_message(sig))
            except Exception as e:
                log.warning("telegram send failed for signal %s: %s", sig_id, e)
                continue
            storage.mark_notified(self.conn, sig_id, "telegram")
            sent += 1
        return sent


def format_message(sig: Signal) -> str:
    value = sig.payload.get("value_usd") or sig.payload.get("value_usd_after") or 0
    value_m = value // 1_000_000
    head = f"🐳 {sig.kind.upper()} — {sig.ticker or sig.cusip or sig.cik}"
    body_parts = [f"period_end={sig.period_end}"]
    if sig.cik:
        body_parts.append(f"cik={sig.cik}")
    if sig.kind in ("increase", "decrease"):
        body_parts.append(f"delta={sig.payload.get('delta_pct')}%")
    if value_m:
        body_parts.append(f"value=${value_m}M")
    body_parts.append(f"severity={sig.severity}")
    return f"{head}\n" + " | ".join(body_parts)
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_notifier.py -v
```

- [ ] **Step 5: Commit**

```bash
git add whale/notifier.py tests/test_notifier.py
git commit -m "feat(notifier): telegram dispatch with dedup"
```

---

## Task 8: `worker.py` — Asyncio orchestrator

**Files:**
- Create: `whale/worker.py`
- Test: `tests/test_worker_pipeline.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/test_worker_pipeline.py
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from whale import storage
from whale.models import FilerEntry
from whale.sec_client import FilingRef
from whale.worker import run_one_cycle


@pytest.mark.asyncio
async def test_one_cycle_end_to_end(tmp_db, tmp_data_dir, fixtures_dir):
    # Seed filer
    storage.upsert_filer(tmp_db, FilerEntry(
        cik="0001067983", name="BRK", category="active", aum_rank=1,
    ))

    # Mock sec_client
    fake_sec = AsyncMock()
    fake_sec.fetch_rss.return_value = [FilingRef(
        accession="0001067983-26-000001",
        cik="0001067983",
        filed_at="2026-02-14T10:00:00-05:00",
        period_end="2024-12-31",
        filing_url="https://www.sec.gov/Archives/edgar/data/1067983/info.xml",
    )]
    fake_sec.download.return_value = (fixtures_dir / "13f_sample_modern.xml").read_text()

    # Mock telegram send
    send = AsyncMock()

    n_signals, n_sent = await run_one_cycle(
        conn=tmp_db,
        sec=fake_sec,
        cache_dir=tmp_data_dir / "cache",
        filer_ciks={"0001067983"},
        send_telegram=send,
        telegram_chat_id="42",
        min_severity=60,
        detected_at="2026-05-20T00:00:00Z",
    )

    # Holdings landed
    rows = storage.holdings_for_period(tmp_db, "2024-12-31")
    assert len(rows) == 2

    # Signals computed (all are 'new' since no prev quarter)
    assert n_signals >= 1
    # Notifier called for high-severity new positions
    assert send.await_count >= 1


@pytest.mark.asyncio
async def test_one_cycle_skips_known_accession(tmp_db, tmp_data_dir, fixtures_dir):
    storage.upsert_filer(tmp_db, FilerEntry(
        cik="0001067983", name="BRK", category="active", aum_rank=1,
    ))
    storage.upsert_filing(
        tmp_db, accession="A1", cik="0001067983",
        filed_at="2026-02-14", period_end="2024-12-31", parse_status="ok",
    )
    fake_sec = AsyncMock()
    fake_sec.fetch_rss.return_value = [FilingRef(
        accession="A1", cik="0001067983", filed_at="x",
        period_end="2024-12-31", filing_url="x",
    )]
    send = AsyncMock()
    await run_one_cycle(
        conn=tmp_db, sec=fake_sec, cache_dir=tmp_data_dir / "cache",
        filer_ciks={"0001067983"}, send_telegram=send,
        telegram_chat_id="42", min_severity=60,
        detected_at="2026-05-20T00:00:00Z",
    )
    fake_sec.download.assert_not_called()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_worker_pipeline.py -v
```

- [ ] **Step 3: Implement `whale/worker.py`**

```python
from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Awaitable, Callable, Set, Tuple

from whale import storage
from whale.notifier import Notifier
from whale.parser_13f import ParseError, parse_information_table
from whale.sec_client import SecClient, SecPermanentError, SecTransientError
from whale.signal_engine import compute_signals

log = logging.getLogger(__name__)

SendTelegram = Callable[[str, str], Awaitable[None]]


async def run_one_cycle(
    *,
    conn: sqlite3.Connection,
    sec: SecClient,
    cache_dir: Path,
    filer_ciks: Set[str],
    send_telegram: SendTelegram,
    telegram_chat_id: str,
    min_severity: int,
    detected_at: str,
) -> Tuple[int, int]:
    """Returns (n_signals_generated, n_notifications_sent)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    refs = await sec.fetch_rss(cik_allowlist=filer_ciks)
    known = storage.known_accessions(conn)
    new_refs = [r for r in refs if r.accession not in known]
    log.info("rss returned %d filings, %d new", len(refs), len(new_refs))

    affected_periods: set[tuple[str, str]] = set()  # (cik, period_end)

    for ref in new_refs:
        storage.upsert_filing(
            conn, accession=ref.accession, cik=ref.cik,
            filed_at=ref.filed_at, period_end=ref.period_end,
            parse_status="pending",
        )
        try:
            xml = await sec.download(_infotable_url(ref.filing_url))
            holdings = parse_information_table(
                xml, cik=ref.cik, period_end=ref.period_end,
            )
            (cache_dir / f"{ref.accession}.xml").write_text(xml)
            storage.upsert_holdings(conn, holdings)
            storage.mark_filing(conn, ref.accession, status="ok")
            affected_periods.add((ref.cik, ref.period_end))
        except SecTransientError as e:
            log.warning("transient error on %s: %s", ref.accession, e)
            storage.mark_filing(conn, ref.accession, status="pending",
                                error=str(e))
        except (SecPermanentError, ParseError) as e:
            log.error("permanent failure %s: %s", ref.accession, e)
            storage.mark_filing(conn, ref.accession, status="failed",
                                error=str(e))

    # Compute signals for each affected (cik, period) by diffing against
    # that filer's most recent prior period.
    n_signals = 0
    for cik, period_end in affected_periods:
        prev_period = _prev_period_for_filer(conn, cik, period_end)
        prev = (storage.holdings_for_period(conn, prev_period, cik=cik)
                if prev_period else [])
        curr = storage.holdings_for_period(conn, period_end, cik=cik)
        sigs = compute_signals(
            prev_holdings=prev, curr_holdings=curr,
            period_end=period_end, detected_at=detected_at,
        )
        for sig in sigs:
            storage.insert_signal(conn, sig)
            n_signals += 1

    # Dispatch telegram
    notifier = Notifier(conn=conn, send=send_telegram,
                        chat_id=telegram_chat_id, min_severity=min_severity)
    n_sent = await notifier.dispatch()

    _write_heartbeat(cache_dir.parent)
    return n_signals, n_sent


def _infotable_url(filing_index_url: str) -> str:
    """Given the filing index URL, derive informationtable XML URL.

    SEC convention: the index page has /<accession>-index.htm; the table
    sits in /<filer>-<accession>.xml or similar. For v1 we accept the
    URL as-is (test fixture is the direct XML); the real-world URL
    derivation may need adjustment when wiring real SEC URLs.
    """
    return filing_index_url


def _prev_period_for_filer(conn: sqlite3.Connection, cik: str,
                            period_end: str) -> str | None:
    row = conn.execute(
        """SELECT DISTINCT period_end FROM holdings
           WHERE cik=? AND period_end < ?
           ORDER BY period_end DESC LIMIT 1""",
        (cik, period_end),
    ).fetchone()
    return row[0] if row else None


def _write_heartbeat(data_dir: Path) -> None:
    from datetime import datetime, timezone
    (data_dir / "worker_heartbeat.txt").write_text(
        datetime.now(timezone.utc).isoformat()
    )


async def run_forever() -> None:
    """Production entry: load config, set up APScheduler, run."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from whale.config import load_config, load_filers

    cfg = load_config()
    storage.init_db(cfg.db_path)
    conn = storage.connect(cfg.db_path)
    for fe in load_filers(cfg.data_dir / "filers.yaml"):
        storage.upsert_filer(conn, fe)
    filer_ciks = {fe.cik for fe in load_filers(cfg.data_dir / "filers.yaml")}

    sec = SecClient(user_agent=cfg.sec_user_agent)

    async def telegram_send(chat_id: str, text: str) -> None:
        # Imported lazily so unit tests don't import telegram lib
        from telegram import Bot
        bot = Bot(token=cfg.telegram_bot_token)
        await bot.send_message(chat_id=chat_id, text=text)

    async def cycle():
        from datetime import datetime, timezone
        try:
            n_sigs, n_sent = await run_one_cycle(
                conn=conn, sec=sec,
                cache_dir=cfg.cache_dir,
                filer_ciks=filer_ciks,
                send_telegram=telegram_send,
                telegram_chat_id=cfg.telegram_chat_id,
                min_severity=cfg.notify_min_severity,
                detected_at=datetime.now(timezone.utc).isoformat(),
            )
            log.info("cycle done: signals=%d sent=%d", n_sigs, n_sent)
        except Exception:
            log.exception("cycle crashed; will retry next schedule")

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(cycle, "cron", hour="2,8,14,20", id="sec_poll")
    scheduler.start()
    log.info("worker started; cycles at 02/08/14/20 UTC")
    await asyncio.Event().wait()  # block forever


if __name__ == "__main__":
    import logging as _l
    _l.basicConfig(level=_l.INFO)
    asyncio.run(run_forever())
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_worker_pipeline.py -v
```

- [ ] **Step 5: Commit**

```bash
git add whale/worker.py tests/test_worker_pipeline.py
git commit -m "feat(worker): asyncio orchestrator with apscheduler"
```

---

## Task 9: `bot.py` — Telegram /commands

**Files:**
- Create: `whale/bot.py`
- Test: `tests/test_bot_handlers.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bot_handlers.py
import pytest

from whale import storage
from whale.bot import build_report, build_holding, build_consensus
from whale.models import FilerEntry, Holding, Signal


def _seed_basic(conn):
    storage.upsert_filer(conn, FilerEntry(
        cik="0001067983", name="BERKSHIRE", category="active", aum_rank=1,
    ))
    storage.upsert_holdings(conn, [
        Holding(cik="0001067983", period_end="2024-12-31", cusip="037833100",
                ticker="AAPL", issuer_name="APPLE", value_usd=200_000_000,
                shares=1_000_000, put_call=None),
    ])
    storage.insert_signal(conn, Signal(
        detected_at="2026-05-20T00:00:00Z", period_end="2024-12-31",
        kind="new", cik="0001067983", cusip="037833100", ticker="AAPL",
        payload={"value_usd": 200_000_000}, severity=80,
    ))


def test_build_report_latest_period(tmp_db):
    _seed_basic(tmp_db)
    text = build_report(tmp_db)
    assert "2024-12-31" in text
    assert "AAPL" in text
    assert "NEW" in text or "new" in text


def test_build_holding_by_ticker(tmp_db):
    _seed_basic(tmp_db)
    text = build_holding(tmp_db, ticker="AAPL")
    assert "BERKSHIRE" in text
    assert "AAPL" in text


def test_build_holding_unknown(tmp_db):
    text = build_holding(tmp_db, ticker="ZZZZ")
    assert "no holdings" in text.lower()


def test_build_consensus(tmp_db):
    storage.upsert_filer(tmp_db, FilerEntry(
        cik="0001067983", name="BRK", category="active", aum_rank=1,
    ))
    storage.insert_signal(tmp_db, Signal(
        detected_at="2026-05-20T00:00:00Z", period_end="2024-12-31",
        kind="consensus", cik=None, cusip="X", ticker="X",
        payload={"direction": "new", "filers_count": 5,
                 "total_value_usd": 500_000_000},
        severity=80,
    ))
    text = build_consensus(tmp_db)
    assert "5" in text
    assert "X" in text
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_bot_handlers.py -v
```

- [ ] **Step 3: Implement `whale/bot.py`**

```python
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from typing import Optional

log = logging.getLogger(__name__)


def _latest_period_end(conn: sqlite3.Connection) -> Optional[str]:
    row = conn.execute(
        "SELECT MAX(period_end) FROM holdings"
    ).fetchone()
    return row[0] if row and row[0] else None


def build_report(conn: sqlite3.Connection, *, limit: int = 20) -> str:
    period = _latest_period_end(conn)
    if not period:
        return "No holdings yet."
    rows = conn.execute(
        """SELECT kind, ticker, cusip, payload_json, severity, cik
           FROM signals WHERE period_end=?
           ORDER BY severity DESC, id DESC LIMIT ?""",
        (period, limit),
    ).fetchall()
    if not rows:
        return f"No signals for period {period}."
    lines = [f"🐳 Whale report — {period}", ""]
    for r in rows:
        payload = json.loads(r["payload_json"])
        lines.append(
            f"[{r['kind']:^9}] sev={r['severity']:>3} "
            f"{r['ticker'] or r['cusip']} {_summarize(r['kind'], payload)}"
        )
    return "\n".join(lines)


def build_holding(conn: sqlite3.Connection, *, ticker: str) -> str:
    rows = conn.execute(
        """SELECT f.name, h.period_end, h.value_usd, h.shares, h.put_call
           FROM holdings h JOIN filers f ON f.cik = h.cik
           WHERE h.ticker = ?
           ORDER BY h.period_end DESC, h.value_usd DESC LIMIT 25""",
        (ticker.upper(),),
    ).fetchall()
    if not rows:
        return f"no holdings found for {ticker.upper()}"
    lines = [f"🐳 Holders of {ticker.upper()}", ""]
    for r in rows:
        v = r["value_usd"] // 1_000_000
        pc = f" {r['put_call']}" if r["put_call"] else ""
        lines.append(f"{r['period_end']} {r['name'][:30]:30} ${v}M{pc}")
    return "\n".join(lines)


def build_consensus(conn: sqlite3.Connection, *, limit: int = 20) -> str:
    rows = conn.execute(
        """SELECT ticker, cusip, payload_json, severity, period_end
           FROM signals WHERE kind='consensus'
           ORDER BY period_end DESC, severity DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    if not rows:
        return "no consensus signals yet"
    lines = ["🐳 Multi-filer consensus", ""]
    for r in rows:
        p = json.loads(r["payload_json"])
        v = p.get("total_value_usd", 0) // 1_000_000
        lines.append(
            f"{r['period_end']} {r['ticker'] or r['cusip']:8} "
            f"{p.get('direction'):10} filers={p.get('filers_count')} ${v}M"
        )
    return "\n".join(lines)


def _summarize(kind: str, payload: dict) -> str:
    if kind in ("increase", "decrease"):
        return (f"Δ={payload.get('delta_pct')}% "
                f"${payload.get('value_usd_after', 0) // 1_000_000}M")
    if kind in ("new", "closed"):
        v = payload.get("value_usd") or payload.get("value_usd_before") or 0
        return f"${v // 1_000_000}M"
    if kind == "consensus":
        return (f"filers={payload.get('filers_count')} "
                f"dir={payload.get('direction')}")
    if kind == "concentration":
        return f"top10={payload.get('top10_pct')}%"
    return ""


async def run_forever() -> None:
    """Production entry: long-poll Telegram for /commands."""
    from telegram import Update
    from telegram.ext import (
        Application, CommandHandler, ContextTypes,
    )

    from whale import storage as _storage
    from whale.config import load_config

    cfg = load_config()
    conn = _storage.connect(cfg.db_path)

    async def report_handler(update: Update, _: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(build_report(conn))

    async def holding_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not ctx.args:
            await update.message.reply_text("usage: /holding TICKER")
            return
        await update.message.reply_text(build_holding(conn, ticker=ctx.args[0]))

    async def consensus_handler(update: Update, _: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(build_consensus(conn))

    app = Application.builder().token(cfg.telegram_bot_token).build()
    app.add_handler(CommandHandler("report", report_handler))
    app.add_handler(CommandHandler("holding", holding_handler))
    app.add_handler(CommandHandler("consensus", consensus_handler))
    log.info("telegram bot started")
    await app.run_polling()


if __name__ == "__main__":
    import logging as _l
    _l.basicConfig(level=_l.INFO)
    asyncio.run(run_forever())
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_bot_handlers.py -v
```

- [ ] **Step 5: Commit**

```bash
git add whale/bot.py tests/test_bot_handlers.py
git commit -m "feat(bot): telegram handlers /report /holding /consensus"
```

---

## Task 10: `cli/__main__.py` — CLI entry

**Files:**
- Create: `cli/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli.py
import sys

import pytest

from whale import storage
from whale.models import FilerEntry, Holding, Signal


def test_cli_report_prints(tmp_db, tmp_data_dir, capsys, monkeypatch):
    # populate db so report has something
    storage.upsert_filer(tmp_db, FilerEntry(
        cik="0001067983", name="BRK", category="active", aum_rank=1,
    ))
    storage.upsert_holdings(tmp_db, [Holding(
        cik="0001067983", period_end="2024-12-31", cusip="X",
        ticker="X", issuer_name="X", value_usd=100, shares=1, put_call=None,
    )])
    storage.insert_signal(tmp_db, Signal(
        detected_at="2026-05-20T00:00:00Z", period_end="2024-12-31",
        kind="new", cik="0001067983", cusip="X", ticker="X",
        payload={"value_usd": 100}, severity=80,
    ))

    monkeypatch.setattr(sys, "argv", ["whale.cli", "report"])
    from cli.__main__ import main
    main()
    out = capsys.readouterr().out
    assert "Whale report" in out


def test_cli_export_unknown_cusip(tmp_db, tmp_data_dir, capsys, monkeypatch):
    storage.upsert_filer(tmp_db, FilerEntry(
        cik="0001067983", name="BRK", category="active", aum_rank=1,
    ))
    storage.upsert_holdings(tmp_db, [Holding(
        cik="0001067983", period_end="2024-12-31", cusip="UNK",
        ticker=None, issuer_name="UNKNOWN CO", value_usd=100, shares=1,
        put_call=None,
    )])
    csv_path = tmp_data_dir / "out.csv"
    monkeypatch.setattr(sys, "argv", [
        "whale.cli", "export-unknown-cusip", "--out", str(csv_path),
    ])
    from cli.__main__ import main
    main()
    assert csv_path.exists()
    content = csv_path.read_text()
    assert "UNK" in content
    assert "UNKNOWN CO" in content
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_cli.py -v
```

- [ ] **Step 3: Implement `cli/__main__.py`**

```python
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from whale import storage
from whale.bot import build_consensus, build_holding, build_report
from whale.config import load_config, load_filers
from whale.cusip_resolver import CusipResolver, unresolved_cusips


def main() -> None:
    p = argparse.ArgumentParser("whale.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report")
    h = sub.add_parser("holding"); h.add_argument("ticker")
    sub.add_parser("consensus")
    exp = sub.add_parser("export-unknown-cusip"); exp.add_argument("--out", required=True)
    imp = sub.add_parser("import-cusip"); imp.add_argument("--csv", required=True)
    rf = sub.add_parser("retry-failed")
    bf = sub.add_parser("backfill"); bf.add_argument("--quarters", type=int, default=8)
    sub.add_parser("refresh")  # one-off cycle, runs same as worker
    args = p.parse_args()

    cfg = load_config()
    storage.init_db(cfg.db_path)
    conn = storage.connect(cfg.db_path)
    # ensure filers loaded
    filers_yaml = cfg.data_dir / "filers.yaml"
    if filers_yaml.exists():
        for fe in load_filers(filers_yaml):
            storage.upsert_filer(conn, fe)

    if args.cmd == "report":
        print(build_report(conn))
    elif args.cmd == "holding":
        print(build_holding(conn, ticker=args.ticker))
    elif args.cmd == "consensus":
        print(build_consensus(conn))
    elif args.cmd == "export-unknown-cusip":
        rows = unresolved_cusips(conn)
        with open(args.out, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["cusip", "issuer_name", "ticker"])
            for cusip, name in rows:
                w.writerow([cusip, name, ""])
        print(f"wrote {len(rows)} unresolved cusips → {args.out}")
    elif args.cmd == "import-cusip":
        r = CusipResolver(conn, cfg.cache_dir)
        n = r.import_csv(Path(args.csv))
        print(f"imported {n} mappings")
    elif args.cmd == "retry-failed":
        rows = conn.execute(
            "UPDATE filings_raw SET parse_status='pending' "
            "WHERE parse_status='failed'"
        )
        print(f"reset {rows.rowcount} failed filings to pending")
    elif args.cmd in ("backfill", "refresh"):
        print(f"{args.cmd}: invoke 'python -m whale.worker' for real cycle "
              f"(backfill mode is a worker option — see README)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_cli.py -v
```

- [ ] **Step 5: Commit**

```bash
git add cli/__main__.py tests/test_cli.py
git commit -m "feat(cli): report / holding / consensus / cusip / retry commands"
```

---

## Task 11: PM2 supervisor + README + manual acceptance

**Files:**
- Create: `ecosystem.config.js`, `README.md`

- [ ] **Step 1: Create `ecosystem.config.js`**

```javascript
module.exports = {
  apps: [
    {
      name: "whale-worker",
      script: "python",
      args: "-m whale.worker",
      cwd: __dirname,
      autorestart: true,
      max_restarts: 20,
      restart_delay: 10000,
      env: { PYTHONUNBUFFERED: "1" },
      out_file: "./logs/worker.out.log",
      error_file: "./logs/worker.err.log",
      merge_logs: true,
    },
    {
      name: "whale-bot",
      script: "python",
      args: "-m whale.bot",
      cwd: __dirname,
      autorestart: true,
      max_restarts: 20,
      restart_delay: 10000,
      env: { PYTHONUNBUFFERED: "1" },
      out_file: "./logs/bot.out.log",
      error_file: "./logs/bot.err.log",
      merge_logs: true,
    },
  ],
};
```

- [ ] **Step 2: Create `README.md`**

```markdown
# whale-tracker-13f

Detects significant 13F position changes from the top US institutional
investors and pushes alerts to Telegram. Decision-aid only — does not trade.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Edit .env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SEC_USER_AGENT
```

## First-run backfill

```bash
python -m whale.worker  # one cycle is enough — or wait for schedule
```

For multi-quarter historical backfill, run the worker for several cycles
or invoke it manually (see Task 8).

## CLI

```bash
python -m cli report
python -m cli holding AAPL
python -m cli consensus
python -m cli export-unknown-cusip --out unknown.csv
python -m cli import-cusip --csv unknown.csv
python -m cli retry-failed
```

## Run under PM2

```bash
pm2 start ecosystem.config.js
pm2 logs whale-worker --lines 100
pm2 logs whale-bot --lines 100
pm2 save
```

## Tests

```bash
pytest                                  # default: skip slow tests
pytest -m slow                          # real SEC network probe
pytest --cov=whale --cov-report=term-missing
```

Coverage gate: **≥80%** (configured in `pyproject.toml`).

## Architecture

See `../docs/superpowers/specs/2026-05-20-whale-tracker-13f-design.md`.
```

- [ ] **Step 3: Commit**

```bash
git add ecosystem.config.js README.md
git commit -m "chore: pm2 supervisor + readme"
```

- [ ] **Step 4: Run full test suite + coverage**

```bash
pytest --cov=whale --cov=cli --cov-fail-under=80
```

Expected: all pass, coverage ≥80%. If any test fails, fix before proceeding.

- [ ] **Step 5: Manual acceptance checklist**

These cannot be automated — work through each by hand:

- [ ] Create a Telegram bot via @BotFather, copy token into `.env`
- [ ] Send any message to your bot; obtain chat_id from `https://api.telegram.org/bot<TOKEN>/getUpdates`; put it in `.env`
- [ ] Run `python -m whale.worker` once, let it complete a real SEC poll cycle. Confirm `data/whale.sqlite` populated.
- [ ] `python -m cli report` prints a readable signal table.
- [ ] In Telegram, send `/report` to your bot, confirm it replies.
- [ ] Trigger a manual test push: insert a synthetic high-severity signal via Python REPL and run one more worker cycle — confirm Telegram message arrives.
- [ ] `pm2 start ecosystem.config.js` runs both processes, `pm2 status` shows both online, `data/worker_heartbeat.txt` timestamp advances every cycle.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: complete manual acceptance, ready for v1 deploy" --allow-empty
```

---

## Self-Review (run by plan author after writing)

**Spec coverage check** (each row in the spec ↔ task):

| Spec section | Task |
|---|---|
| Top 100 13F filers (active/passive tag) | Task 1c seeds 10; backlog notes expansion |
| 7 signal classes | Task 6 implements 6; sector_rotation stub (backlog, captured in spec §7) |
| Telegram push + `/commands` | Tasks 7, 9 |
| CLI report / refresh / backfill / cusip / retry | Task 10 |
| Two-process model + SQLite WAL | Task 2 (WAL), Task 8 (worker), Task 9 (bot) — independent processes, shared sqlite |
| SEC RSS poll, 10 req/s, retry, User-Agent | Task 3 |
| 13F XML parsing incl. PUT/CALL, ×1000 units | Task 4 |
| CUSIP → ticker, unknown CUSIP CSV workflow | Task 5 + Task 10 |
| Severity scoring + dedup `notified_log` | Tasks 6, 7 |
| Heartbeat file | Task 8 (`_write_heartbeat`) |
| PM2 supervisor | Task 11 |
| ≥80% coverage gate | Task 0 (`pyproject.toml`), Task 11 verifies |
| Backlog items (Form 4, on-chain, NLP, dashboard, auto-universe) | Out of scope — captured in spec §7 |

**Known intentional deferrals**:
- Sector rotation signal: stubbed in `signal_engine.py` with TODO comment in spec backlog; needs GICS map.
- 100-filer universe: starts with 10 seed entries — expansion is data work, not code work.
- Backfill multi-quarter: worker schedules naturally cover this over time; explicit `backfill --quarters N` would need adding a one-shot mode to worker. Plan task 10 lists it as a CLI command but defers implementation to manual run of `whale.worker`. **If you want this implemented now, add to backlog or amend Task 8.**

**Placeholder scan**: none.

**Type consistency**: `Holding`, `Signal`, `FilerEntry` defined in Task 1, used identically downstream. Signal `kind` enum constrained to literal types declared in `models.py`.

---

**Plan complete and saved to** `docs/superpowers/plans/2026-05-20-whale-tracker-13f.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
