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
