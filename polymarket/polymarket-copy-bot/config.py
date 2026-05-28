"""Polymarket copy-trading bot configuration."""
import os
from dotenv import load_dotenv

load_dotenv()

# API endpoints
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
LB_API = "https://lb-api.polymarket.com"

# Chain
CHAIN_ID = 137

# Wallet
PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")
FUNDER_ADDRESS = os.getenv("POLYMARKET_FUNDER_ADDRESS", "")
SIGNATURE_TYPE = int(os.getenv("SIGNATURE_TYPE", "1"))

# Copy strategy
COPY_AMOUNT_USD = float(os.getenv("COPY_AMOUNT_USD", "5"))
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", "50"))

# G3 risk control: cap on simultaneous OPEN positions (0 or empty = disabled)
_max_open = os.getenv("MAX_OPEN_POSITIONS", "20").strip()
MAX_OPEN_POSITIONS = int(_max_open) if _max_open and int(_max_open) > 0 else None

# G4 risk control: cap per source_trader (0 or empty = disabled)
_max_per_trader = os.getenv("MAX_OPEN_PER_TRADER", "5").strip()
MAX_OPEN_PER_TRADER = (int(_max_per_trader)
                       if _max_per_trader and int(_max_per_trader) > 0
                       else None)

# Ranker
RANK_WINDOW_DAYS = int(os.getenv("RANK_WINDOW_DAYS", "90"))
RANK_WEIGHTS = tuple(float(w) for w in os.getenv("RANK_WEIGHTS", "0.3,0.3,0.4").split(","))
RANK_CANDIDATE_POOL_SIZE = int(os.getenv("RANK_CANDIDATE_POOL_SIZE", "50"))
RANK_MAX_ACTIVITY_PER_USER = int(os.getenv("RANK_MAX_ACTIVITY_PER_USER", "3000"))
MIN_RESOLVED_MARKETS = int(os.getenv("MIN_RESOLVED_MARKETS", "20"))
MIN_LIFETIME_VOLUME_USD = float(os.getenv("MIN_LIFETIME_VOLUME_USD", "1000"))
MIN_LAST_TRADE_DAYS = int(os.getenv("MIN_LAST_TRADE_DAYS", "14"))
# Absolute thresholds: "best traders" must be profitable winners
MIN_TOTAL_PNL_USD = float(os.getenv("MIN_TOTAL_PNL_USD", "0"))
MIN_WIN_RATE = float(os.getenv("MIN_WIN_RATE", "0.5"))
# Rank smoothing: order traders by rolling average of their raw composite
# score over the last N days (0 disables -> use today's score only).
RANK_SMOOTHING_DAYS = int(os.getenv("RANK_SMOOTHING_DAYS", "3"))

# Watcher
POLL_INTERVAL_SEC = int(os.getenv("POLL_INTERVAL_SEC", "30"))
# Odds filter: skip OPEN signals outside this price band (extreme-odds markets
# give sub-cent returns on a small fixed copy). 0/1 disables filtering.
MIN_ODDS = float(os.getenv("MIN_ODDS", "0.05"))
MAX_ODDS = float(os.getenv("MAX_ODDS", "0.95"))

# Storage
DB_PATH = os.getenv("DB_PATH", "data/bot.sqlite")
SIGNALS_JSONL_PATH = os.getenv("SIGNALS_JSONL_PATH", "data/signals.jsonl")

# Polymarket minimum order size (USDC)
MIN_ORDER_USD = 1.0
