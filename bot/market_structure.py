"""Market structure: HH / HL / LH / LL (spec item 3).

The one rule that matters here is *when* a swing becomes known. A swing high at
bar i is only confirmed once `window` bars have printed to its right — at bar i
itself nobody can tell it is a high. Every swing therefore carries
`confirmed_at`, and `structure_at()` looks only at swings confirmed by the bar
being asked about. Without that the backtest reads the future and every number
it produces is worthless (spec item 39).

Structure that is not clearly bullish or bearish returns 0, which the spec says
must mean WAIT, not "pick the better-looking side".
"""
from dataclasses import dataclass

import pandas as pd

from .config import Params, DEFAULT_PARAMS

BULLISH, BEARISH, UNCLEAR = 1, -1, 0
HIGH, LOW = "high", "low"


@dataclass(frozen=True)
class Swing:
    time: pd.Timestamp       # when the swing printed
    price: float
    kind: str                # HIGH or LOW
    confirmed_at: pd.Timestamp   # the first bar at which it could be known


def find_swings(df: pd.DataFrame, p: Params = DEFAULT_PARAMS) -> list[Swing]:
    """Fractal swing points: a bar whose high is the highest of the `window`
    bars on each side (and the mirror for lows)."""
    w = p.swing_window
    highs, lows = df["high"], df["low"]
    # center=True compares each bar against both sides; the result is only
    # usable `w` bars later, which `confirmed_at` records.
    is_high = highs == highs.rolling(2 * w + 1, center=True).max()
    is_low = lows == lows.rolling(2 * w + 1, center=True).min()

    out: list[Swing] = []
    index = df.index
    for pos, ts in enumerate(index):
        confirm_pos = pos + w
        if confirm_pos >= len(index):
            break  # not confirmable yet with the data we have
        confirmed_at = index[confirm_pos]
        if bool(is_high.iloc[pos]):
            out.append(Swing(ts, float(highs.iloc[pos]), HIGH, confirmed_at))
        if bool(is_low.iloc[pos]):
            out.append(Swing(ts, float(lows.iloc[pos]), LOW, confirmed_at))
    return out


def confirmed_by(swings: list[Swing], when: pd.Timestamp) -> list[Swing]:
    """The swings a decision made at `when` is allowed to see."""
    return [s for s in swings if s.confirmed_at <= when]


def structure_at(swings: list[Swing], when: pd.Timestamp,
                 p: Params = DEFAULT_PARAMS) -> int:
    """BULLISH (HH+HL), BEARISH (LH+LL) or UNCLEAR, as of `when`."""
    visible = confirmed_by(swings, when)
    highs = [s for s in visible if s.kind == HIGH][-2:]
    lows = [s for s in visible if s.kind == LOW][-2:]
    if len(highs) < 2 or len(lows) < 2:
        return UNCLEAR
    higher_high = highs[-1].price > highs[-2].price
    higher_low = lows[-1].price > lows[-2].price
    if higher_high and higher_low:
        return BULLISH
    if not higher_high and not higher_low:
        return BEARISH
    return UNCLEAR   # one up, one down: no clean structure


def last_swing(swings: list[Swing], when: pd.Timestamp, kind: str) -> Swing | None:
    """Most recent confirmed swing of a kind — where a structural stop goes."""
    found = [s for s in confirmed_by(swings, when) if s.kind == kind]
    return found[-1] if found else None


def structure_series(df: pd.DataFrame, p: Params = DEFAULT_PARAMS) -> pd.Series:
    """Structure per bar, for the backtester and for measuring how often the
    market is actually readable."""
    swings = find_swings(df, p)
    # Walk forward once instead of re-filtering the whole list per bar.
    highs: list[float] = []
    lows: list[float] = []
    by_confirm: dict[pd.Timestamp, list[Swing]] = {}
    for s in swings:
        by_confirm.setdefault(s.confirmed_at, []).append(s)

    values = []
    for ts in df.index:
        for s in by_confirm.get(ts, ()):
            (highs if s.kind == HIGH else lows).append(s.price)
        if len(highs) < 2 or len(lows) < 2:
            values.append(UNCLEAR)
            continue
        hh, hl = highs[-1] > highs[-2], lows[-1] > lows[-2]
        values.append(BULLISH if (hh and hl) else BEARISH if (not hh and not hl) else UNCLEAR)
    return pd.Series(values, index=df.index, name="structure")
