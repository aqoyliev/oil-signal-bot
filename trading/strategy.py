"""Signal rules — Bollinger mean reversion on 4h candles.

  * BUY  when a candle closes below the lower Bollinger band and RSI < rsi_low.
  * SELL when a candle closes above the upper band and RSI > 100 - rsi_low.

Each signal becomes a zone setup (see setups.py):
  * Zone 1 starts at the signal price, zone 2 sits zone2_offset_atr deeper.
  * Stop-loss: sl_atr * ATR beyond each zone's edge.
  * TP1..TP4 at tp_frac of the way to the middle band (TP4 = the band).
  * After TP1 the stop moves to entry (break-even). Pending zones expire
    after zone_valid_hours, open ones are closed after max_hold_hours.

Decisions use only CLOSED candles, so a signal never repaints.
Parameters were chosen on the first 70% of 2 years of data and checked
on the remaining 30% (see README).
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .indicators import atr, bollinger, rsi


@dataclass
class Params:
    bb_period: int = 20
    bb_mult: float = 2.0
    rsi_period: int = 14
    rsi_low: float = 30.0
    # zone setup
    zone_atr: float = 0.3            # zone width
    zone2_offset_atr: float = 0.75   # zone 2 distance from zone 1
    sl_atr: float = 3.0              # stop distance from the zone edge
    tp_frac: tuple = (0.25, 0.5, 0.75, 1.0)
    min_target_atr: float = 0.5      # floor for the distance to the target
    zone_valid_hours: float = 12
    max_hold_hours: float = 48
    # "price is getting close" heads-up, sent before a real signal.
    # Chosen from 2 years of data: ~3 alerts per instrument per month, about a
    # third of which turn into a real signal within 20h. Looser settings fire
    # 3x as often without improving that share.
    approach_band: float = 0.0       # share of the band half-width left to the band
    approach_rsi: float = 5.0        # RSI margin before the signal level


DEFAULT_PARAMS = Params()


def compute_signals(df: pd.DataFrame, p: Params = DEFAULT_PARAMS) -> pd.DataFrame:
    """Adds indicator columns and `signal`: 1 = BUY, -1 = SELL, 0 = nothing."""
    df = df.copy()
    df["bb_low"], df["bb_mid"], df["bb_up"] = bollinger(df["Close"], p.bb_period, p.bb_mult)
    df["rsi"] = rsi(df["Close"], p.rsi_period)
    df["atr"] = atr(df)
    buy = (df["Close"] < df["bb_low"]) & (df["rsi"] < p.rsi_low)
    sell = (df["Close"] > df["bb_up"]) & (df["rsi"] > 100 - p.rsi_low)
    df["signal"] = np.where(buy, 1, np.where(sell, -1, 0))
    # `approach`: not a signal yet, but close enough to warn the user
    half = df["bb_mid"] - df["bb_low"]
    near_buy = (df["Close"] <= df["bb_low"] + p.approach_band * half) & \
               (df["rsi"] <= p.rsi_low + p.approach_rsi)
    near_sell = (df["Close"] >= df["bb_up"] - p.approach_band * half) & \
                (df["rsi"] >= 100 - p.rsi_low - p.approach_rsi)
    df["approach"] = np.where(df["signal"] != 0, 0, np.where(near_buy, 1, np.where(near_sell, -1, 0)))
    df.iloc[:50, df.columns.get_loc("signal")] = 0  # indicators not warmed up yet
    df.iloc[:50, df.columns.get_loc("approach")] = 0
    return df
