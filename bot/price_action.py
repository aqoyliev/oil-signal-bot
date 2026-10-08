"""Candle-level confirmation (spec item 6).

Price action here is a filter, never a reason on its own: it answers "does this
candle support the direction the rest of the analysis already picked?" Every
measurement is relative to ATR, so the same rules work on $30 oil and $130 oil
without retuning.

Spec item 6 also asks for the negative case — no entries on tiny candles or in
dead consolidation — which is `is_dead()`.

Columns are produced for the whole frame at once (`annotate`) so the backtester
does not pay per-bar pandas costs; `score()` then reads a single row.
"""
import numpy as np
import pandas as pd

from .config import Params, DEFAULT_PARAMS

FEATURES = ("body", "range", "upper_wick", "lower_wick", "close_pos",
            "body_atr", "range_atr", "engulf_up", "engulf_down", "expansion")


def annotate(df: pd.DataFrame, p: Params = DEFAULT_PARAMS) -> pd.DataFrame:
    """Add the price-action columns. `df` must already carry `atr`."""
    out = df.copy()
    o, h, l, c = out["open"], out["high"], out["low"], out["close"]
    rng = (h - l).replace(0, np.nan)

    out["body"] = (c - o).abs()
    out["range"] = h - l
    out["upper_wick"] = h - c.combine(o, max)
    out["lower_wick"] = c.combine(o, min) - l
    # 1.0 = closed at the high, 0.0 = closed at the low
    out["close_pos"] = ((c - l) / rng).fillna(0.5)
    out["body_atr"] = out["body"] / out["atr"]
    out["range_atr"] = out["range"] / out["atr"]

    prev_o, prev_c = o.shift(), c.shift()
    prev_top = prev_o.combine(prev_c, max)
    prev_bottom = prev_o.combine(prev_c, min)
    bull, bear = c > o, c < o
    out["engulf_up"] = bull & (prev_c < prev_o) & (c >= prev_top) & (o <= prev_bottom)
    out["engulf_down"] = bear & (prev_c > prev_o) & (c <= prev_bottom) & (o >= prev_top)

    baseline = out["range"].rolling(p.pa_range_window).mean().shift()
    out["expansion"] = (out["range"] / baseline).fillna(1.0)
    return out


def is_dead(row, p: Params = DEFAULT_PARAMS) -> bool:
    """Dead candle — spec item 6 says do not enter here."""
    return bool(row.body_atr < p.pa_dead_atr)


def strong_candle(row, direction: int, p: Params = DEFAULT_PARAMS) -> bool:
    """Big body closing near the extreme in the traded direction."""
    if row.body_atr < p.pa_body_atr:
        return False
    return bool(row.close_pos >= p.pa_close_frac) if direction == 1 \
        else bool(row.close_pos <= 1 - p.pa_close_frac)


def engulfing(row, direction: int) -> bool:
    return bool(row.engulf_up) if direction == 1 else bool(row.engulf_down)


def rejection_wick(row, direction: int, p: Params = DEFAULT_PARAMS) -> bool:
    """A long wick against the direction, i.e. the move was rejected there:
    for a BUY, a long *lower* wick means sellers failed."""
    body = max(float(row.body), 1e-9)
    wick = float(row.lower_wick) if direction == 1 else float(row.upper_wick)
    return wick / body >= p.pa_wick_ratio


def momentum_expansion(row, p: Params = DEFAULT_PARAMS) -> bool:
    return bool(row.expansion >= p.pa_expansion)


def score(row, direction: int, p: Params = DEFAULT_PARAMS) -> float:
    """0.0 to 1.0 for the five points of spec item 12.

    A dead candle scores zero outright rather than collecting partial credit,
    because item 6 treats it as a reason to stay out.
    """
    if is_dead(row, p):
        return 0.0
    checks = (
        strong_candle(row, direction, p),
        engulfing(row, direction),
        rejection_wick(row, direction, p),
        momentum_expansion(row, p),
    )
    # A candle rarely ticks every box; two of four is already good confirmation.
    return min(1.0, sum(checks) / 2.0)


def describe(row, direction: int, p: Params = DEFAULT_PARAMS) -> list[str]:
    """What fired, for the signal message and the log (spec item 35)."""
    if is_dead(row, p):
        return ["dead candle"]
    names = []
    if strong_candle(row, direction, p):
        names.append("strong candle")
    if engulfing(row, direction):
        names.append("engulfing")
    if rejection_wick(row, direction, p):
        names.append("rejection wick")
    if momentum_expansion(row, p):
        names.append("momentum expansion")
    return names or ["no confirmation"]
