"""The five indicators of spec item 2, plus ADX for the market-condition filter
(spec item 27).

All of them use Wilder smoothing where that is the standard definition, so the
numbers match what the trader sees in TradingView or MT5. Every function takes
and returns plain pandas objects and looks only at past bars — nothing here may
peek at the candle it is being asked about, or the backtest becomes fiction.

Note on MFI: the CFD feed reports *tick* volume, not exchange contract volume.
MFI is therefore a proxy. Spec item 12 gives it 10 of 100 points; whether it
earns them is a question for the backtester (spec items 31, 39), not for this
module.
"""
import numpy as np
import pandas as pd

from .config import Params, DEFAULT_PARAMS


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _wilder(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing — the average used by RSI, ATR and ADX."""
    return series.ewm(alpha=1 / period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = _wilder(delta.clip(lower=0), period)
    loss = _wilder((-delta).clip(lower=0), period)
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(100.0).where(gain + loss > 0, 50.0)  # flat market: neutral


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift()
    return pd.concat([df["high"] - df["low"],
                      (df["high"] - prev_close).abs(),
                      (df["low"] - prev_close).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return _wilder(true_range(df), period)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd line, signal line, histogram) — spec item 2."""
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Money Flow Index — RSI weighted by volume (spec item 2)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    flow = typical * df["volume"]
    rising = typical.diff() > 0
    positive = flow.where(rising, 0.0).rolling(period).sum()
    negative = flow.where(~rising, 0.0).rolling(period).sum()
    ratio = positive / negative.replace(0, np.nan)
    out = 100 - 100 / (1 + ratio)
    return out.fillna(50.0)  # no volume on either side tells us nothing


def adx(df: pd.DataFrame, period: int = 14):
    """Returns (adx, +di, -di). Below `adx_trending` the market is ranging."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = _wilder(true_range(df), period).replace(0, np.nan)
    plus_di = 100 * _wilder(plus_dm, period) / tr
    minus_di = 100 * _wilder(minus_dm, period) / tr
    total = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / total
    return _wilder(dx.fillna(0.0), period), plus_di.fillna(0.0), minus_di.fillna(0.0)


def compute(df: pd.DataFrame, p: Params = DEFAULT_PARAMS) -> pd.DataFrame:
    """Attach every indicator column the scoring engine needs.

    The leading rows where the slow EMA is not warmed up yet are dropped: an
    EMA200 built from 30 bars is a number, but it is not an EMA200, and scoring
    on it would inflate the backtest.
    """
    out = df.copy()
    out["ema_fast"] = ema(out["close"], p.ema_fast)
    out["ema_mid"] = ema(out["close"], p.ema_mid)
    out["ema_slow"] = ema(out["close"], p.ema_slow)
    out["rsi"] = rsi(out["close"], p.rsi_period)
    out["mfi"] = mfi(out, p.mfi_period)
    out["macd"], out["macd_signal"], out["macd_hist"] = macd(
        out["close"], p.macd_fast, p.macd_slow, p.macd_signal)
    out["atr"] = atr(out, p.atr_period)
    out["atr_pct"] = 100 * out["atr"] / out["close"]
    out["adx"], out["di_plus"], out["di_minus"] = adx(out, p.adx_period)
    return out.iloc[p.ema_slow:]


def ema_bias(row) -> int:
    """1 bullish, -1 bearish, 0 mixed — the strict stack of spec item 2."""
    if row.ema_fast > row.ema_mid > row.ema_slow:
        return 1
    if row.ema_fast < row.ema_mid < row.ema_slow:
        return -1
    return 0
