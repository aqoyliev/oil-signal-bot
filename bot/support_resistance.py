"""Support/resistance levels and the breakout+retest setup (spec items 4, 5).

Levels are built from *confirmed* swings only (see market_structure), clustered
so that a zone touched four times is one level with four touches rather than
four levels. A level's `confirmed_at` is the confirmation time of the earliest
swing in the cluster, so a decision never uses a level it could not have drawn.

The breakout+retest detector implements item 5 literally: close beyond the
level, return to it, level holds. It deliberately does *not* fire on a wick
that merely touched the level.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Params, DEFAULT_PARAMS
from .market_structure import HIGH, LOW, Swing, confirmed_by

RESISTANCE, SUPPORT = "resistance", "support"


@dataclass(frozen=True)
class Level:
    price: float
    kind: str                     # RESISTANCE (from swing highs) or SUPPORT (from lows)
    touches: int
    confirmed_at: pd.Timestamp
    last_touch: pd.Timestamp

    def distance(self, price: float) -> float:
        return abs(self.price - price)


@dataclass(frozen=True)
class BreakoutRetest:
    level: Level
    direction: int                # 1 = resistance broken upward, -1 = support broken down
    broke_at: pd.Timestamp
    retest_at: pd.Timestamp | None
    holds: bool                   # the broken level still holds as new support/resistance

    @property
    def complete(self) -> bool:
        """A tradable setup: broken, retested and holding (spec item 5)."""
        return self.retest_at is not None and self.holds


def build_levels(swings: list[Swing], when: pd.Timestamp, atr_value: float,
                 p: Params = DEFAULT_PARAMS, since: pd.Timestamp | None = None) -> list[Level]:
    """Cluster confirmed swings into levels.

    `since` bounds the history, which matters more than it looks: without it
    every swing of the last six months stays a level forever, the list grows
    past a hundred entries and `blocked()` then refuses every entry because
    some level is always a few cents away.
    """
    visible = confirmed_by(swings, when)
    if since is not None:
        visible = [s for s in visible if s.time >= since]
    tolerance = p.sr_merge_atr * atr_value
    out: list[Level] = []
    for kind, swing_kind in ((RESISTANCE, HIGH), (SUPPORT, LOW)):
        group = sorted((s for s in visible if s.kind == swing_kind), key=lambda s: s.price)
        cluster: list[Swing] = []
        for s in group:
            if cluster and s.price - cluster[0].price > tolerance:
                out.append(_as_level(cluster, kind))
                cluster = []
            cluster.append(s)
        if cluster:
            out.append(_as_level(cluster, kind))
    strong = [lv for lv in out if lv.touches >= p.sr_min_touches]
    # Keep the most-respected levels; ties go to the more recently touched one.
    strong.sort(key=lambda lv: (lv.touches, lv.last_touch), reverse=True)
    return strong[:p.sr_max_levels]


def _as_level(cluster: list[Swing], kind: str) -> Level:
    prices = [s.price for s in cluster]
    return Level(
        price=sum(prices) / len(prices),
        kind=kind,
        touches=len(cluster),
        confirmed_at=min(s.confirmed_at for s in cluster),
        last_touch=max(s.time for s in cluster),
    )


def previous_day_levels(daily: pd.DataFrame, when: pd.Timestamp) -> tuple[float, float] | None:
    """Previous day's high and low (spec item 4), from closed daily candles."""
    past = daily[daily.index < when.normalize()]
    if past.empty:
        return None
    row = past.iloc[-1]
    return float(row["high"]), float(row["low"])


def nearest_above(levels: list[Level], price: float) -> Level | None:
    above = [lv for lv in levels if lv.price > price]
    return min(above, key=lambda lv: lv.price) if above else None


def nearest_below(levels: list[Level], price: float) -> Level | None:
    below = [lv for lv in levels if lv.price < price]
    return max(below, key=lambda lv: lv.price) if below else None


def blocked(direction: int, price: float, levels: list[Level], atr_value: float,
            p: Params = DEFAULT_PARAMS) -> Level | None:
    """The level standing in the way, if any.

    Spec item 4: no BUY directly under strong resistance, no SELL directly
    above strong support. Returns the offending level so the caller can say why
    it refused.
    """
    limit = p.sr_block_atr * atr_value
    target = nearest_above(levels, price) if direction == 1 else nearest_below(levels, price)
    if target is None:
        return None
    too_close = target.distance(price) < limit
    return target if (too_close and target.touches >= p.sr_min_touches) else None


class LevelBook:
    """Swings and levels maintained one bar at a time — the single engine the
    backtester and the live bot both run.

    Why it is incremental: recomputing swings from scratch on every bar is
    O(bars²) and does not finish on the five years of 15m candles spec item 29
    asks for. Swings are detected once (they carry `confirmed_at`, so that is
    still look-ahead-safe) and levels are re-clustered from the bounded
    lookback window, which holds tens of swings rather than hundreds.

    Why the breakout is *not* tracked as per-level state: a level's price is
    its cluster's mean, so the moment a new swing joins the cluster the price
    moves and any state keyed to it is lost. An earlier version did exactly
    that and silently dropped 7 of 25 sampled breakouts. The breakout is
    instead derived each bar from the current levels over the last
    `retest_window` bars, which is one rule in one place.
    """

    def __init__(self, df: pd.DataFrame, swings: list[Swing], p: Params = DEFAULT_PARAMS):
        self.df = df
        self.p = p
        self._pending: dict[pd.Timestamp, list[Swing]] = {}
        for s in swings:
            self._pending.setdefault(s.confirmed_at, []).append(s)
        self._seen: list[Swing] = []
        self.levels: list[Level] = []
        self._pos = -1
        self.now: pd.Timestamp | None = None
        self._atr = float("nan")
        # Pandas scalar access costs about a microsecond a go, which at twelve
        # levels times a twenty-bar window turns into minutes over a 175k-bar
        # backtest. The arrays are extracted once.
        self._times = df.index
        self._close = df["close"].to_numpy(dtype=float)
        self._high = df["high"].to_numpy(dtype=float)
        self._low = df["low"].to_numpy(dtype=float)

    @property
    def _since(self) -> pd.Timestamp | None:
        """Start of the lookback window, counted in bars actually seen, so a
        weekend gap does not silently widen it."""
        if self._pos + 1 < self.p.sr_lookback:
            return None
        return self._times[self._pos + 1 - self.p.sr_lookback]

    def advance(self, pos: int, atr_value: float):
        """Move to bar `pos`. Afterwards the book reflects bars up to and
        including it, and nothing later."""
        self._pos = pos
        self.now = self._times[pos]
        self._atr = atr_value
        newly = self._pending.get(self.now)
        if newly:
            self._seen.extend(newly)
        since = self._since
        if since is not None:
            self._seen = [s for s in self._seen if s.time >= since]
        # Rebuilt every bar: the merge tolerance is a multiple of ATR, which
        # moves with every candle, so caching the levels would quietly leave
        # them clustered at a stale volatility. The window keeps the swing
        # count in the tens, so this is cheap.
        self.levels = build_levels(self._seen, self.now, atr_value, self.p, since)

    @property
    def breakout(self) -> BreakoutRetest | None:
        """The most recent live break-and-retest (spec item 5), or None."""
        if self._pos < 2:
            return None
        start = max(0, self._pos - (self.p.retest_window + 1))
        stop = self._pos + 1
        return _breakout_core(self._times[start:stop], self._close[start:stop],
                              self._high[start:stop], self._low[start:stop],
                              self.levels, self._atr, self.p)


def find_breakout_retest(df: pd.DataFrame, levels: list[Level], atr_value: float,
                         p: Params = DEFAULT_PARAMS) -> BreakoutRetest | None:
    """The most recent break-and-retest in `df`, or None — the entry point for
    one-off use. `df` must end at the bar being decided on."""
    w = df.iloc[-(p.retest_window + 2):]
    return _breakout_core(w.index, w["close"].to_numpy(dtype=float),
                          w["high"].to_numpy(dtype=float), w["low"].to_numpy(dtype=float),
                          levels, atr_value, p)


def _breakout_core(times, close, high, low, levels: list[Level], atr_value: float,
                   p: Params) -> BreakoutRetest | None:
    """The one implementation of spec item 5, vectorised per level."""
    if len(close) < 3 or not levels:
        return None
    clearance = p.breakout_close_atr * atr_value
    retest_room = p.retest_atr * atr_value

    best: BreakoutRetest | None = None
    for level in levels:
        direction = 1 if level.kind == RESISTANCE else -1
        # A level cannot be broken before it could be drawn.
        first = int(np.searchsorted(times, level.confirmed_at, side="left"))
        if len(close) - first < 2:
            continue
        seg = close[first:]
        beyond = level.price + direction * clearance
        if direction == 1:
            crossings = np.flatnonzero((seg[1:] > beyond) & (seg[:-1] <= level.price))
        else:
            crossings = np.flatnonzero((seg[1:] < beyond) & (seg[:-1] >= level.price))
        if crossings.size == 0:
            continue
        broke = first + int(crossings[-1]) + 1      # position of the breaking close
        if best is not None and times[broke] <= best.broke_at:
            continue

        after = slice(broke + 1, len(close))
        if direction == 1:
            back = np.flatnonzero(low[after] <= level.price + retest_room)
            lost = bool(np.any(close[after] < level.price - clearance))
        else:
            back = np.flatnonzero(high[after] >= level.price - retest_room)
            lost = bool(np.any(close[after] > level.price + clearance))
        retest_at = times[broke + 1 + int(back[0])] if back.size else None
        best = BreakoutRetest(level, direction, times[broke], retest_at, holds=not lost)
    return best
