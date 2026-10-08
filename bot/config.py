"""Every tunable parameter in one place (spec items 24, 28, 31).

Secrets and deployment settings come from the environment (`.env`); strategy
parameters live in the `Params` dataclass so the backtester and the optimizer
can sweep them with `dataclasses.replace(p, rsi_period=21)` without touching
module state. Nothing in here reads market data or decides anything — it only
holds numbers.
"""
from dataclasses import dataclass, field

from environs import Env

env = Env()
env.read_env()

# --- secrets and deployment (spec item 32: keys never live in code) ---
BOT_TOKEN = env.str("BOT_TOKEN")
ADMINS = env.list("ADMINS")
ANTHROPIC_API_KEY = env.str("ANTHROPIC_API_KEY", "")   # news sentiment, chart analysis
EIA_API_KEY = env.str("EIA_API_KEY", "")               # actual inventory numbers
DB_PATH = env.str("DB_PATH", "")                       # mounted volume in production
CACHE_DIR = env.str("CACHE_DIR", "")                   # historical candle cache
TZ = env.str("TZ", "Asia/Tashkent")                    # how times are shown to users

# --- instruments (spec item 1, 7, 8) ---
# DXY is context only: it scores a setup, it never produces one of its own.
SYMBOLS = ("WTI", "BRENT")
DXY = "DXY"

# --- timeframes (spec items 1, 14) ---
TREND_TF = "1h"    # major trend
SETUP_TF = "30m"   # primary setup
ENTRY_TF = "15m"   # entry refinement


@dataclass(frozen=True)
class Params:
    # --- indicators (spec item 2) ---
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    mfi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14

    # RSI is momentum confirmation, never an entry on its own (spec item 2)
    rsi_bull: float = 50.0
    rsi_bull_strong: tuple = (55.0, 70.0)
    rsi_bear_strong: tuple = (30.0, 45.0)
    mfi_bull: float = 50.0
    mfi_bull_strong: float = 60.0
    mfi_bear_strong: float = 40.0

    # --- market structure (spec item 3) ---
    swing_window: int = 5          # bars each side of a confirmed swing point
    structure_swings: int = 4      # how many recent swings define the structure

    # --- support / resistance (spec item 4) ---
    # A level is only a level if price respected it recently and more than once.
    # Measured on 30m WTI: a 0.5-ATR merge over an unbounded history produced
    # 167 levels six months in, which blocked practically every entry. The
    # lookback and the level cap are what keep the list meaningful.
    sr_lookback: int = 400         # bars searched for levels
    sr_merge_atr: float = 1.5      # levels closer than this (in ATR) are one level
    sr_min_touches: int = 2
    sr_max_levels: int = 12        # keep the most-touched, drop the rest
    sr_block_atr: float = 1.0      # "directly under resistance" distance

    # --- price action (spec item 6), all sizes relative to ATR ---
    pa_body_atr: float = 0.5       # a "strong" candle's body
    pa_dead_atr: float = 0.2       # below this the candle says nothing
    pa_close_frac: float = 0.65    # close must sit this far up/down its range
    pa_wick_ratio: float = 1.5     # rejection wick vs body
    pa_range_window: int = 20      # baseline for momentum expansion
    pa_expansion: float = 1.4      # range vs that baseline

    # --- correlation and DXY (spec items 7, 8) ---
    corr_conflict_penalty: float = 0.5   # score kept when WTI and Brent disagree
    dxy_strong_atr: float = 1.0          # DXY move that counts as "strongly" against

    # --- breakout + retest (spec item 5) ---
    breakout_close_atr: float = 0.25   # close must clear the level by this much
    retest_window: int = 20            # bars allowed between break and retest
    retest_atr: float = 0.5            # how close the retest must come back

    # --- entry zone (the band quoted in the message, spec item 22) ---
    entry_zone_atr: float = 0.15   # half-width of the zone around the price

    # --- stop loss (spec item 16) ---
    sl_atr_buffer: float = 0.5     # ATR buffer beyond the swing, never on the level
    sl_min_atr: float = 0.8        # floor, so a tight swing cannot give a silly SL

    # --- risk/reward and targets (spec items 17, 18) ---
    rr_min: float = 2.0            # below this: no trade
    rr_by_score: tuple = ((75, 2.0), (80, 3.0), (85, 4.0), (90, 5.0), (95, 6.0))
    tp_rr: tuple = (2.0, 3.0, 5.0, 6.0)
    tp_share: tuple = (0.25, 0.25, 0.25, 0.25)
    breakeven_after_tp: int = 1    # move SL to entry after TP1
    trail_after_tp: int = 2        # start trailing after TP2 (spec item 19)
    trail_atr: float = 2.0         # loose on oil, it swings intraday

    # --- scoring weights, total 100 (spec item 12) ---
    w_structure: float = 15
    w_ema: float = 15
    w_rsi: float = 10
    w_mfi: float = 10
    w_macd: float = 10
    w_sr: float = 10
    w_breakout: float = 10
    w_price_action: float = 5
    w_correlation: float = 5
    w_dxy: float = 5
    w_news: float = 5

    # --- score thresholds (spec item 13) ---
    score_min: float = 75          # below this: no signal
    score_watch: float = 65        # 65-74 is a watch, not a trade
    score_strong: float = 80
    score_very_strong: float = 85
    score_a_plus: float = 90

    # --- news (spec items 10, 11) ---
    blackout_before_min: int = 15
    blackout_after_min: int = 5
    news_score_max: int = 3        # the -3..+3 scale
    news_veto: int = -2            # news this contradictory blocks the trade

    # --- volatility / market condition filter (spec item 27) ---
    atr_pct_min: float = 0.15      # ATR below this share of price: too quiet
    atr_pct_max: float = 1.50      # above this: too wild
    adx_period: int = 14
    adx_trending: float = 20.0     # below this the market is ranging

    # --- frequency and duplicates (spec items 20, 21) ---
    max_signals_per_day: int = 3
    cooldown_bars: int = 8         # on the setup timeframe
    daily_limit_resets_at: str = "00:00"   # in TZ

    # --- risk management (spec items 24, 26) ---
    risk_per_trade: float = 0.5    # percent of balance
    max_daily_loss: float = 2.0    # percent; after this, no signals until reset
    account_balance: float = 1000.0

    # --- sessions (spec item 28), local exchange hours in UTC ---
    # Not disabled by default: the spec says to weight, not to switch off untested.
    sessions: dict = field(default_factory=lambda: {
        "asian": (0, 8),
        "london": (7, 16),
        "newyork": (12, 21),
    })
    session_weight: dict = field(default_factory=lambda: {
        "asian": 0.8, "london": 1.0, "newyork": 1.0,
    })

    def rr_for_score(self, score: float) -> float:
        """Highest RR the score earns (spec items 17, 37)."""
        allowed = [rr for threshold, rr in self.rr_by_score if score >= threshold]
        return max(allowed) if allowed else self.rr_min


DEFAULT_PARAMS = Params()
