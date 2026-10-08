"""Multi-timeframe alignment and the decision loop (spec item 14).

Not in the spec's module list, but the alignment has to live somewhere shared:
the live monitor and the backtester must build identical snapshots, or the
backtest stops describing the bot. Putting it here keeps `signal_engine` pure
and stops the backtester from becoming the only place that knows how the
timeframes line up.

The alignment rule, which is where look-ahead creeps into every multi-timeframe
system: a bar is usable only once it has **closed**. A 30-minute bar opening at
10:00 closes at 10:30, so a decision taken at 10:15 may not see it — it must
use the bar that opened at 09:30. Frames are therefore re-keyed by close time
and joined backwards with `merge_asof`, which makes the mistake impossible
rather than merely unlikely.

Decisions run on 15m closes (item 1: 15M refines entry), with the last closed
30m bar as the setup context and the last closed 1h bar as the trend.
"""
from dataclasses import dataclass

import pandas as pd

from . import correlation as corr
from . import indicators as ind
from . import market_structure as ms
from . import news_engine as ne
from . import price_action as pa
from . import signal_engine as se
from .config import ENTRY_TF, Params, DEFAULT_PARAMS, SETUP_TF, TREND_TF
from .data_provider import TIMEFRAMES, DataProvider
from .support_resistance import LevelBook


@dataclass
class Frames:
    """One instrument, prepared on all three timeframes."""
    symbol: str
    entry: pd.DataFrame      # 15m, with indicators and price action
    setup: pd.DataFrame      # 30m, same
    trend: pd.DataFrame      # 1h, indicators only
    setup_structure: pd.Series
    trend_structure: pd.Series
    setup_swings: list


def prepare(provider: DataProvider, symbol: str, start, end,
            p: Params = DEFAULT_PARAMS) -> Frames:
    def load(tf, with_pa):
        df = ind.compute(provider.candles(symbol, tf, start, end), p)
        return pa.annotate(df, p) if with_pa else df

    entry = load(ENTRY_TF, True)
    setup = load(SETUP_TF, True)
    trend = load(TREND_TF, False)
    return Frames(symbol, entry, setup, trend,
                  ms.structure_series(setup, p), ms.structure_series(trend, p),
                  ms.find_swings(setup, p))


def _by_close(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Re-key a frame by the moment each bar closed."""
    out = df.copy()
    out["_open_time"] = out.index
    out.index = out.index + TIMEFRAMES[timeframe]
    out.index.name = "close_time"
    return out


def align(frames: Frames, other: Frames | None, dxy: pd.DataFrame | None,
          p: Params = DEFAULT_PARAMS) -> pd.DataFrame:
    """One row per 15m close, carrying only already-closed higher-timeframe bars."""
    entry = _by_close(frames.entry, ENTRY_TF)
    setup = _by_close(frames.setup, SETUP_TF)
    trend = _by_close(frames.trend, TREND_TF)

    setup = setup.assign(_structure=frames.setup_structure.to_numpy())
    trend = trend.assign(_structure=frames.trend_structure.to_numpy())

    merged = pd.merge_asof(
        entry.reset_index().sort_values("close_time"),
        setup.reset_index().sort_values("close_time"),
        on="close_time", direction="backward", suffixes=("", "_setup"))
    merged = pd.merge_asof(
        merged.sort_values("close_time"),
        trend.reset_index().sort_values("close_time")[
            ["close_time", "_structure", "ema_fast", "ema_mid", "ema_slow", "close"]],
        on="close_time", direction="backward", suffixes=("", "_trend"))

    if other is not None:
        other_setup = _by_close(other.setup, SETUP_TF).assign(
            _structure=other.setup_structure.to_numpy())
        merged = pd.merge_asof(
            merged.sort_values("close_time"),
            other_setup.reset_index().sort_values("close_time")[
                ["close_time", "_structure", "ema_fast", "ema_mid", "ema_slow"]],
            on="close_time", direction="backward", suffixes=("", "_other"))
    if dxy is not None:
        d = _by_close(dxy, SETUP_TF)
        merged = pd.merge_asof(
            merged.sort_values("close_time"),
            d.reset_index().sort_values("close_time")[
                ["close_time", "close", "ema_fast", "ema_mid", "ema_slow", "atr"]],
            on="close_time", direction="backward", suffixes=("", "_dxy"))
    return merged.set_index("close_time")


def _int_or_unclear(value) -> int:
    """A missing or NaN structure reads as UNCLEAR, which means WAIT."""
    return ms.UNCLEAR if value is None or pd.isna(value) else int(value)


class _Row:
    """Attribute access over a suffixed slice of the merged row."""

    def __init__(self, row, suffix: str = ""):
        self._row, self._suffix = row, suffix

    def __getattr__(self, name: str):
        key = f"{name}{self._suffix}"
        if key in self._row:
            return self._row[key]
        if name in self._row:
            return self._row[name]
        raise AttributeError(f"{name!r} not in the aligned row (looked for {key!r})")


def scan(frames: Frames, merged: pd.DataFrame, events: list[ne.Event],
         p: Params = DEFAULT_PARAMS):
    """Yield (close_time, direction, Signal | Rejection) for every 15m close.

    The level book advances on the setup timeframe as its bars close, so the
    levels a decision sees are exactly the ones that existed then.
    """
    book = LevelBook(frames.setup, frames.setup_swings, p)
    setup_pos = -1
    setup_index = frames.setup.index
    setup_atr = frames.setup["atr"].to_numpy()

    for close_time, row in merged.iterrows():
        setup_open = row.get("_open_time_setup")
        if setup_open is None or pd.isna(setup_open):
            continue
        # Advance the book to the setup bar this decision is allowed to see.
        target = int(setup_index.get_indexer([setup_open])[0])
        while setup_pos < target:
            setup_pos += 1
            book.advance(setup_pos, float(setup_atr[setup_pos]))

        entry_row = _Row(row)
        setup_row = _Row(row, "_setup")
        trend_row = _Row(row, "_trend")
        # The grades do not start on the same bar and one feed can be short of
        # the other, so an absent column is UNCLEAR rather than an error.
        structure = _int_or_unclear(row.get("_structure"))
        trend_structure = _int_or_unclear(row.get("_structure_trend"))
        if structure == ms.UNCLEAR:
            continue   # item 3: no structure, no trade — and nothing to score
        other_bias = ms.UNCLEAR
        other_structure = _int_or_unclear(row.get("_structure_other"))
        if other_structure is not None and "ema_fast_other" in row \
                and not pd.isna(row["ema_fast_other"]):
            other_bias = corr.instrument_bias(_Row(row, "_other"), other_structure)
        dxy_bias, dxy_strong = ms.UNCLEAR, False
        if "close_dxy" in row and not pd.isna(row["close_dxy"]):
            dxy_bias, dxy_strong = corr.dxy_bias_from(_Row(row, "_dxy"), p)
        context = corr.Context(other_bias, dxy_bias, dxy_strong)
        points = ne.news_score(events, close_time, p=p)

        for direction in (1, -1):
            snap = se.Snapshot(
                symbol=frames.symbol, when=close_time, direction=direction,
                setup_row=setup_row, trend_row=trend_row, entry_row=entry_row,
                setup_structure=structure,
                trend_structure=trend_structure,
                levels=book.levels, breakout=book.breakout,
                context=context, news=events, news_points=points)
            yield close_time, direction, se.evaluate(snap, p)
