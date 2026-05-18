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
