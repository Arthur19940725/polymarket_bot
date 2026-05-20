# Whale Tracker — 13F Institutional Holdings (Design Spec)

- **Date**: 2026-05-20
- **Owner**: xu505483585@gmail.com
- **Status**: Approved (brainstorming → design)
- **Project**: `C:\Users\Arthur\workspace\polymarket\whale-tracker-13f` (new sibling repo, decoupled from `polymarket-copy-bot`)

## 1. Goal & Scope

Build a detection + dashboard bot that tracks the largest US institutional investors' quarterly holdings (SEC 13F filings) and surfaces their position changes as actionable signals. **Decision aid only — does not place trades.**

### In scope (this spec)
- Track Top 100 13F filers by AUM (Buffett / Bridgewater / Pershing / Tiger Global / Renaissance / ...), with active vs passive tag so passive index funds don't drown out conviction money.
- Detect four signal classes per quarterly refresh:
  - New position / closed position
  - Significant increase / decrease (±25% delta_pct threshold)
  - Multi-filer consensus (N filers move same direction same quarter)
  - Concentration / sector rotation
- Two delivery channels: **Telegram bot** (real-time push + interactive `/commands`) and **CLI** (`python -m whale.cli`).
- Backfill 8 quarters on first deploy so diffs and consensus have history.

### Out of scope (separate sub-projects, captured as backlog)
- Form 4 insider trades (next sub-project — reuses SEC fetch layer)
- On-chain crypto Smart Money wallets
- Celebrity tweet / interview NLP
- Unified cross-source aggregation dashboard

## 2. Architecture — Two-process model

Worker (long-running SEC poller + signal engine) and Telegram bot (long-running command responder) are **two separate Python processes** that share state through a single SQLite database in WAL mode. CLI is a third on-demand entry point that reads the same DB.

```
┌─────────────────────────────────────────────────────────────┐
│  whale-tracker-13f/                                         │
│                                                             │
│  ┌─────────────────┐         ┌──────────────────┐           │
│  │  worker进程      │         │ telegram_bot进程  │           │
│  │  python -m       │         │ python -m         │          │
│  │  whale.worker    │         │ whale.bot         │          │
│  │                  │         │                   │          │
│  │  - clock 调度    │         │  - long-poll      │          │
│  │  - sec_client    │         │  - /report        │          │
│  │  - parser_13f    │         │  - /holding TIC   │          │
│  │  - signal_engine │         │  - /consensus     │          │
│  │  - notifier ─────┼─────────┼─→ Bot API         │          │
│  └────────┬─────────┘         └─────────┬─────────┘          │
│           │                              │                   │
│           ▼                              ▼                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   SQLite (WAL) data/whale.sqlite                     │   │
│  │   filers / filings_raw / holdings / signals /        │   │
│  │   cusip_ticker / notified_log                        │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  cli/  →  python -m whale.cli report|refresh|backfill        │
└──────────────────────────────────────────────────────────────┘
```

**Key decisions**:
- **CUSIP → ticker**: Use SEC `company_tickers.json` as the primary map (free, official, ~95% coverage). Unmatched CUSIPs land in a `cusip_ticker_unknown` view; CLI exports them for manual fill.
- **Universe maintenance**: `data/filers.yaml` holds 100 entries `(cik, name, category, aum_rank)`. AUM rank rarely changes — manual maintenance is sufficient for v1; auto-refresh is backlog.
- **Process coordination**: SQLite WAL only. No queue, no IPC framework. `notified_log` table prevents duplicate Telegram pushes.
- **Process supervision**: PM2 (already installed on host) runs both processes; auto-restart on crash.

## 3. Component breakdown

```
whale-tracker-13f/
├── whale/
│   ├── __init__.py
│   ├── config.py          # env + filers.yaml loader; only mutable global
│   ├── storage.py         # SQLite schema + connection management (WAL)
│   ├── sec_client.py      # SEC HTTP client: RSS + single filing download
│   │                      #   - User-Agent / 10 req/s rate limit
│   │                      #   - retry + cache (accession-hit skip)
│   ├── parser_13f.py      # pure function: XML/XBRL → list[Holding dataclass]
│   ├── cusip_resolver.py  # CUSIP → ticker; refreshes company_tickers.json
│   ├── signal_engine.py   # pure function: (prev_q, curr_q) → list[Signal]
│   │                      #   - new_position / closed
│   │                      #   - delta_pct (±25%)
│   │                      #   - consensus (cross-filer aggregation)
│   │                      #   - concentration / sector_rotation
│   ├── notifier.py        # Signal → Telegram message; writes notified_log
│   ├── worker.py          # asyncio main loop: clock → fetch → parse → signal → notify
│   └── bot.py             # telegram bot: handlers call read-only storage views
├── cli/
│   └── __main__.py        # python -m whale.cli {report|refresh|backfill|export-unknown-cusip|retry-failed}
├── data/
│   ├── whale.sqlite
│   ├── filers.yaml
│   └── cache/             # raw SEC filing XML cache
├── tests/
│   ├── fixtures/
│   └── test_*.py
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── ecosystem.config.js    # PM2 config for both processes
└── README.md
```

**Dependency direction (unidirectional)**:

```
worker.py ──┬─→ sec_client ──→ HTTP
            ├─→ parser_13f       (pure)
            ├─→ cusip_resolver ──→ storage
            ├─→ signal_engine    (pure)
            ├─→ notifier ────→ Telegram API
            └─→ storage

bot.py ─────→ storage (read-only views)

cli/__main__ → storage + signal_engine + cusip_resolver
```

**Boundary rationale**:
- `parser_13f` and `signal_engine` are pure functions → unit-testable with fixtures, no mocks.
- `sec_client` is the only IO boundary → mock the whole module in tests.
- `storage` is the state boundary → tests use a temp sqlite file.
- `worker.py` and `bot.py` are thin orchestrators — no business logic — covered by integration tests.

**Runtime dependencies**:
- `httpx[async]` — async HTTP client
- `python-telegram-bot v21` — async Telegram API
- `lxml` — 13F XBRL/XML parsing
- `pydantic v2` — dataclass + validation
- `apscheduler` — worker scheduling (mirrors polymarket-copy-bot)
- `pytest` + `pytest-asyncio` (dev)

## 4. Data model & flow

### 4.1 SQLite schema (WAL mode)

```sql
CREATE TABLE filers (
  cik          TEXT PRIMARY KEY,        -- "0001067983"
  name         TEXT NOT NULL,
  category     TEXT NOT NULL,           -- 'active' | 'passive'
  aum_rank     INTEGER,
  notes        TEXT
);

CREATE TABLE filings_raw (
  accession    TEXT PRIMARY KEY,        -- "0001067983-26-000123"
  cik          TEXT NOT NULL,
  filed_at     TEXT NOT NULL,           -- ISO8601
  period_end   TEXT NOT NULL,           -- "2026-03-31"
  fetched_at   TEXT NOT NULL,
  parse_status TEXT NOT NULL,           -- 'pending'|'ok'|'failed'
  parse_error  TEXT,
  FOREIGN KEY (cik) REFERENCES filers(cik)
);
CREATE INDEX idx_filings_cik_period ON filings_raw(cik, period_end);

CREATE TABLE holdings (
  cik          TEXT NOT NULL,
  period_end   TEXT NOT NULL,
  cusip        TEXT NOT NULL,
  ticker       TEXT,
  issuer_name  TEXT NOT NULL,
  value_usd    INTEGER NOT NULL,        -- 13F reports in thousands, stored as USD (×1000)
  shares       INTEGER NOT NULL,
  put_call     TEXT,                    -- NULL | 'PUT' | 'CALL'
  PRIMARY KEY (cik, period_end, cusip, put_call)
);
CREATE INDEX idx_holdings_cusip_period ON holdings(cusip, period_end);

CREATE TABLE signals (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  detected_at   TEXT NOT NULL,
  period_end    TEXT NOT NULL,
  kind          TEXT NOT NULL,          -- 'new'|'closed'|'increase'|'decrease'|'consensus'|'concentration'|'sector_rotation'
  cik           TEXT,                   -- NULL for cross-filer signals
  cusip         TEXT,
  ticker        TEXT,
  payload_json  TEXT NOT NULL,
  severity      INTEGER NOT NULL        -- 0..100
);
CREATE INDEX idx_signals_period_kind ON signals(period_end, kind);

CREATE TABLE cusip_ticker (
  cusip        TEXT PRIMARY KEY,
  ticker       TEXT NOT NULL,
  source       TEXT NOT NULL,           -- 'sec'|'manual'
  updated_at   TEXT NOT NULL
);

CREATE TABLE notified_log (
  signal_id    INTEGER PRIMARY KEY,
  notified_at  TEXT NOT NULL,
  channel      TEXT NOT NULL            -- 'telegram'
);
```

### 4.2 Worker scheduled cycle (4x/day, default 02/08/14/20 UTC)

```
1. sec_client.fetch_rss(cik_list)
      → [(accession, cik, filed_at, period_end)]
2. For each accession not in filings_raw:
   a. sec_client.download_filing(accession) → raw XML to data/cache/
   b. parser_13f.parse(xml) → list[Holding]
   c. cusip_resolver.batch_resolve(cusips) → fill ticker
   d. storage.upsert_filing + holdings; filings_raw.parse_status='ok'
3. If a period_end gained new filers this round:
   signal_engine.compute(period_end, prev_period_end) → write signals
4. notifier.dispatch():
   SELECT signals not in notified_log AND severity ≥ NOTIFY_MIN_SEVERITY
   → push Telegram, write notified_log
```

### 4.3 Signal severity scoring

- `new` / `closed` with value ≥ $100M → severity 70+
- `increase` / `decrease`: severity scales with delta_pct and absolute USD value
- `consensus`: more concurrent filers → higher severity
- User-configurable `.env` setting `NOTIFY_MIN_SEVERITY=60`

### 4.4 Backfill

- First deploy: `python -m whale.cli backfill --quarters 8` populates 2 years of history
- Subsequent quarters fill in via worker schedule

### 4.5 Idempotency & failure handling

- All writes use `INSERT OR IGNORE` / `UPSERT` — re-fetching an accession has no side effects.
- Parse failures mark `parse_status='failed'` with error message; CLI `retry-failed` re-tries.
- Telegram push failure: do not write `notified_log` → next round retries naturally; per-signal retry capped at 10/24h.

## 5. Error handling & reliability

### SEC HTTP layer (`sec_client.py`)
- Mandatory `User-Agent: "whale-tracker (xu505483585@gmail.com)"` — SEC requires it or bans the IP.
- Global token bucket: **10 req/s** (SEC fair-use ceiling), shared across the module.
- httpx timeouts: connect 5s / read 30s.
- Retry: 429 / 5xx / network errors → exponential backoff 1s/2s/4s/8s, max 4 attempts. Then raise `SecTransientError`; worker skips that accession this round, picks it up next round.
- Non-429 4xx → raise `SecPermanentError`; mark `parse_status='failed'`, no further retries.

### Parser layer (`parser_13f.py`)
- 13F format has multiple historical versions (pre-2013 HTML, 2013+ XML, 2022+ XBRL inline) → sniff schema, branch parser.
- Missing/malformed fields → raise `ParseError(accession, reason)`. Affected filing marked `failed`; siblings in the same batch unaffected.
- Test fixtures cover all 3 historical formats.

### CUSIP resolution
- SEC `company_tickers.json` refreshed weekly, cached at `data/cache/`.
- Unmatched CUSIPs: `ticker=NULL` in holdings. Surfaced via `cusip_ticker_unknown` view.
- CLI: `export-unknown-cusip` writes CSV; `import-cusip cusips.csv` ingests manual fills.
- Never blocks signal generation — fall back to `issuer_name` for display.

### Signal engine (`signal_engine.py`)
- Pure function: either computes or raises; no recovery needed.
- On first run with no prev_q: skip diff signals, emit only `new` (every position is "new" by definition).

### Notifier (`notifier.py`)
- Telegram API failure: do not write notified_log → automatic retry next round. Per-signal cap: 10 retries / 24h to prevent storms.
- Message > 4096 chars → auto-split.
- After N consecutive failures, mark signal `severity_capped` to prevent backlog.

### Process-level
- Worker main loop wrapped in `try / except / log / sleep(60)`. Single-round exceptions never kill the process.
- Heartbeat: each round writes `data/worker_heartbeat.txt` (timestamp). External monitor can alarm on staleness.
- PM2 manages both processes with auto-restart.

### Logging
- Structured JSON → `logs/worker.log` / `logs/bot.log`, daily rotation.
- Key events: new filing, parse failure, signal generated, push result.

### Rate & quota
- SEC: 10 req/s ceiling. Worst case: 100 filers × ~1 filing each per quarter window = trivial load.
- Telegram bot API: 30 msg/s global. Quarter-window peak ~100 signals/day, far below limit.

### Security & credentials
- `.env` only stores: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `NOTIFY_MIN_SEVERITY`, `LOG_LEVEL`.
- `.env` excluded via `.gitignore` (inherits pattern from polymarket-copy-bot).
- **No trading credentials anywhere** — this project never places orders.

## 6. Test strategy

Goal: **≥80% coverage**, three-layer pyramid mirroring polymarket-copy-bot's TDD style.

### Unit tests (largest, fastest)
- `test_parser_13f.py`: fixtures for 3 historical 13F formats (2010 HTML / 2018 XML / 2024 XBRL) → assert exact Holding list against expected JSON.
- `test_signal_engine.py`: synthesized `(prev_q, curr_q)` inputs cover boundary conditions for all 7 signal kinds — especially ±25% threshold, 0→X triggers `new`, X→0 triggers `closed`.
- `test_cusip_resolver.py`: mock company_tickers.json response; verify cache hit, manual fallback.
- `test_storage.py`: temp sqlite; verify upsert idempotency, notified_log dedup, WAL cross-process visibility.

### Integration tests
- `test_worker_pipeline.py`: mock `sec_client`'s RSS + filing downloads; run full fetch → parse → diff → signal → notify chain; assert final DB state and Telegram call count.
- `test_bot_handlers.py`: use `python-telegram-bot`'s test helper to simulate `/report`, `/holding BRK`, `/consensus`; assert reply contents.

### Smoke / E2E (optional, marker: `slow`)
- `test_e2e_real_sec.py`: hits SEC RSS for real (no DB writes, no pushes); verifies sec_client still works against current SEC response shape. Run nightly in CI; skipped in dev.

### Test fixtures
- `tests/fixtures/13f_berkshire_2024q4.xml` (trimmed to top 20 holdings)
- `tests/fixtures/13f_bridgewater_2024q4.xml`
- `tests/fixtures/rss_sample.xml`
- `tests/fixtures/cusips_partial.json`
- `tests/fixtures/holdings_prev_q.json` / `holdings_curr_q.json`

### Must-cover edge cases (easy to get wrong)
1. Same CUSIP reused across quarters for the same issuer → diff math correct.
2. PUT/CALL options vs shares are distinct holding rows → diff cannot mix them.
3. Filer amends mid-quarter (`13F-HR/A`) → use the latest accession only.
4. `value_usd` unit conversion: 13F reports thousands; multiply ×1000 (off-by-1000 is a classic bug).
5. SQLite WAL cross-process: worker writes, bot must see immediately.

### CI / local
- `requirements-dev.txt`: pytest, pytest-asyncio, pytest-cov, freezegun, respx (httpx mock).
- `pytest -q --cov=whale --cov-fail-under=80` runs as pre-commit hook.
- `conftest.py` style mirrors polymarket-copy-bot.

### Manual acceptance checklist (self-verify before reporting "done")
- [ ] `python -m whale.cli backfill --quarters 4` completes; sqlite contains real Berkshire holdings on SELECT.
- [ ] `python -m whale.cli report` prints a readable quarter-over-quarter diff report.
- [ ] Worker runs one real poll round with zero errors.
- [ ] A manually triggered Telegram test push arrives in chat.
- [ ] `/report` command in Telegram replies correctly.

## 7. Backlog (future sub-projects, separate spec/plan cycles)

1. **Form 4 insider trades** — reuses SEC fetch layer + storage pattern.
2. **On-chain Smart Money wallets** — new stack (Etherscan / Dune / Arkham); independent project.
3. **Celebrity tweet / interview NLP** — X API + sentiment + entity extraction; highest noise.
4. **Unified aggregation dashboard** — once at least two of the above are running, build a cross-source web dashboard.
5. **Auto-refresh universe** — replace manual `filers.yaml` with quarterly AUM-rank recomputation.
