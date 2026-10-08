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


class _Columns:
    """The merged frame as plain numpy arrays.

    Reading scalars off a wide pandas Series is about a microsecond a field,
    which over 11 000 bars times two directions times a dozen fields was most
    of a 15-minute scan. The same scan over arrays is seconds.
    """

    __slots__ = ("data", "index")

    def __init__(self, df: pd.DataFrame):
        self.data = {name: df[name].to_numpy() for name in df.columns}
        self.index = df.index

    def array(self, name: str):
        return self.data.get(name)


class _Row:
    """A positional view of one row, resolving `name` then `name<suffix>`."""

    __slots__ = ("_cols", "_pos", "_suffix")

    def __init__(self, cols: _Columns, pos: int, suffix: str = ""):
        self._cols, self._pos, self._suffix = cols, pos, suffix

    def __getattr__(self, name: str):
        data = self._cols.data
        column = data.get(name + self._suffix)
        if column is None:
            column = data.get(name)
        if column is None:
            raise AttributeError(
                f"{name!r} not in the aligned row (looked for {name + self._suffix!r})")
        return column[self._pos]


def scan(frames: Frames, merged: pd.DataFrame, events: list[ne.Event],
         p: Params = DEFAULT_PARAMS):
    """Yield (close_time, direction, Signal | Rejection) for every 15m close.

    Every row is evaluated, including the ones item 3 refuses outright, so the
    tally of refusal reasons is complete — skipping them here would hide the
    single most common reason the bot stays out.

    The level book advances on the setup timeframe as its bars close, so the
    levels a decision sees are exactly the ones that existed then.
    """
    cols = _Columns(merged)
    book = LevelBook(frames.setup, frames.setup_swings, p)
    setup_atr = frames.setup["atr"].to_numpy()

    # Which setup bar each decision may see, resolved once instead of per row.
    # -1 marks a row with no closed setup bar behind it yet.
    setup_for_row = frames.setup.index.get_indexer(cols.array("_open_time_setup"))
    structures = cols.array("_structure")
    trend_structures = cols.array("_structure_trend")
    other_ema = cols.array("ema_fast_other")
    other_structures = cols.array("_structure_other")
    dxy_close = cols.array("close_dxy")

    setup_pos = -1
    breakout = None
    for pos, close_time in enumerate(cols.index):
        target = int(setup_for_row[pos])
        if target < 0:
            continue
        if target > setup_pos:
            while setup_pos < target:
                setup_pos += 1
                book.advance(setup_pos, float(setup_atr[setup_pos]))
            # Levels only move when a setup bar closes, so the breakout is
            # derived once per setup bar rather than per 15m decision.
            breakout = book.breakout

        entry_row = _Row(cols, pos)
        setup_row = _Row(cols, pos, "_setup")
        trend_row = _Row(cols, pos, "_trend")

        # The grades do not start on the same bar and one feed can run short of
        # the other, so an absent column reads as UNCLEAR rather than failing.
        other_bias = ms.UNCLEAR
        if other_ema is not None and not pd.isna(other_ema[pos]):
            other_struct = None if other_structures is None else other_structures[pos]
            other_bias = corr.instrument_bias(_Row(cols, pos, "_other"),
                                              _int_or_unclear(other_struct))
        dxy_bias, dxy_strong = ms.UNCLEAR, False
        if dxy_close is not None and not pd.isna(dxy_close[pos]):
            dxy_bias, dxy_strong = corr.dxy_bias_from(_Row(cols, pos, "_dxy"), p)
        context = corr.Context(other_bias, dxy_bias, dxy_strong)
        points = ne.news_score(events, close_time, p=p)

        for direction in (1, -1):
            snap = se.Snapshot(
                symbol=frames.symbol, when=close_time, direction=direction,
                setup_row=setup_row, trend_row=trend_row, entry_row=entry_row,
                setup_structure=_int_or_unclear(structures[pos]),
                trend_structure=_int_or_unclear(trend_structures[pos]),
                levels=book.levels, breakout=breakout,
                context=context, news=events, news_points=points)
            yield close_time, direction, se.evaluate(snap, p)
