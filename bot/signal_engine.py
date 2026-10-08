"""Scoring and the final decision (spec items 12, 13, 14, 15, 16, 17, 18, 37).

The engine is deliberately pure: `evaluate()` takes a `Snapshot` of everything
already measured at one moment and returns either a `Signal` or a `Rejection`
saying which rule refused. No data fetching, no clock, no I/O — that is what
makes the same call usable from the live monitor and from the backtester, and
what makes item 39's question answerable at all.

Two kinds of rule, kept apart on purpose:

  * **Vetoes** — item 3's unclear structure, item 14's "do not trade against
    the 1H trend", item 10's blackout, item 17's unreachable 1:2. These are not
    points to be outvoted; a setup that trips one is not a trade at any score.
  * **Score** — item 12's weighted 0-100, which only ranks the setups that
    already passed every veto.

Collapsing the two would let a 95-point setup trade into a news blackout, which
is exactly what item 10 forbids.
"""
from dataclasses import dataclass, field

from . import correlation as corr
from . import news_engine as ne
from . import price_action as pa
from .config import Params, DEFAULT_PARAMS
from .indicators import ema_bias
from .market_structure import BULLISH, UNCLEAR
from .support_resistance import BreakoutRetest, Level, blocked, nearest_above, nearest_below

# Grades of spec item 13
NO_TRADE, WATCH, VALID, STRONG, VERY_STRONG, A_PLUS = (
    "NO_TRADE", "WATCH", "VALID", "STRONG", "VERY_STRONG", "A+")


@dataclass(frozen=True)
class Component:
    """One line of the item 12 table: what it was worth and what it scored."""
    name: str
    weight: float
    value: float          # 0.0 to 1.0
    note: str = ""

    @property
    def points(self) -> float:
        return self.weight * self.value


@dataclass(frozen=True)
class Snapshot:
    """Everything the engine is allowed to know at one moment."""
    symbol: str
    when: object                      # pd.Timestamp
    direction: int                    # the side being tested: 1 BUY, -1 SELL
    setup_row: object                 # 30m bar with indicators + price action
    trend_row: object                 # 1h bar with indicators
    entry_row: object                 # 15m bar with indicators + price action
    setup_structure: int
    trend_structure: int
    levels: list[Level]
    breakout: BreakoutRetest | None
    context: corr.Context
    news: list[ne.Event] = field(default_factory=list)
    news_points: int = ne.NEUTRAL_SCORE


@dataclass(frozen=True)
class Signal:
    symbol: str
    direction: int
    when: object
    entry_low: float
    entry_high: float
    sl: float
    tps: list[tuple[float, float]]    # (rr, price), nearest first
    score: float
    grade: str
    rr_cap: float                     # the realistic ceiling, before grading
    components: list[Component]
    notes: list[str]

    @property
    def entry_price(self) -> float:
        """The price the plan is measured from — the far edge of the zone, so
        the risk is not understated."""
        return self.entry_high if self.direction == 1 else self.entry_low

    @property
    def risk(self) -> float:
        return abs(self.entry_price - self.sl)


@dataclass(frozen=True)
class Rejection:
    reason: str
    score: float = 0.0
    components: list[Component] = field(default_factory=list)
    grade: str = NO_TRADE


# --- individual score components (spec item 12) -----------------------------
def _structure_value(structure: int, direction: int) -> float:
    return 1.0 if structure == direction else 0.0


def _ema_value(row, direction: int) -> tuple[float, str]:
    """Full credit for item 2's strict stack, partial when only the fast pair
    agrees — a pullback inside a trend should not score the same as a reversal."""
    strict = ema_bias(row)
    if strict == direction:
        return 1.0, "stacked"
    if strict == -direction:
        return 0.0, "stacked against"
    fast_pair = (row.ema_fast > row.ema_mid) if direction == 1 else (row.ema_fast < row.ema_mid)
    return (0.5, "fast pair only") if fast_pair else (0.2, "mixed")


def _rsi_value(row, direction: int, p: Params) -> tuple[float, str]:
    value = float(row.rsi)
    lo, hi = p.rsi_bull_strong if direction == 1 else p.rsi_bear_strong
    if direction == 1:
        if value < p.rsi_bull:
            return 0.0, f"{value:.0f} below 50"
        if lo <= value <= hi:
            return 1.0, f"{value:.0f} in the strong band"
        # Above the strong band the move is late, not better (item 2).
        return (0.5, f"{value:.0f} overbought") if value > hi else (0.6, f"{value:.0f} bullish")
    if value > p.rsi_bull:
        return 0.0, f"{value:.0f} above 50"
    if lo <= value <= hi:
        return 1.0, f"{value:.0f} in the strong band"
    return (0.5, f"{value:.0f} oversold") if value < lo else (0.6, f"{value:.0f} bearish")


def _mfi_value(row, direction: int, p: Params) -> tuple[float, str]:
    value = float(row.mfi)
    if direction == 1:
        if value < p.mfi_bull:
            return 0.0, f"{value:.0f} below 50"
        return (1.0, f"{value:.0f} strong") if value >= p.mfi_bull_strong else (0.6, f"{value:.0f}")
    if value > p.mfi_bull:
        return 0.0, f"{value:.0f} above 50"
    return (1.0, f"{value:.0f} strong") if value <= p.mfi_bear_strong else (0.6, f"{value:.0f}")


def _macd_value(row, direction: int) -> tuple[float, str]:
    above = float(row.macd) > float(row.macd_signal)
    hist_ok = float(row.macd_hist) > 0 if direction == 1 else float(row.macd_hist) < 0
    agrees = above if direction == 1 else not above
    if not agrees:
        return 0.0, "cross against"
    return (1.0, "cross and histogram") if hist_ok else (0.7, "cross only")


def _sr_value(price: float, levels: list[Level], atr_value: float, direction: int,
              p: Params) -> tuple[float, str]:
    """Location quality: close to the level that should hold, far from the one
    in the way (spec item 4)."""
    behind = nearest_below(levels, price) if direction == 1 else nearest_above(levels, price)
    ahead = nearest_above(levels, price) if direction == 1 else nearest_below(levels, price)
    if behind is None:
        return 0.3, "no level behind"
    support_distance = behind.distance(price) / max(atr_value, 1e-9)
    room = (ahead.distance(price) / max(atr_value, 1e-9)) if ahead else 99.0
    close_enough = support_distance <= p.sr_block_atr
    has_room = room >= p.sr_block_atr * 2
    if close_enough and has_room:
        return 1.0, f"{behind.touches}-touch level {support_distance:.1f} ATR behind"
    if has_room:
        return 0.6, f"level {support_distance:.1f} ATR behind"
    return 0.2, "little room ahead"


def _breakout_value(breakout: BreakoutRetest | None, direction: int) -> tuple[float, str]:
    if breakout is None or breakout.direction != direction:
        return 0.0, "none"
    if breakout.complete:
        return 1.0, "broken, retested, holding"
    if breakout.holds:
        return 0.5, "broken, no retest yet"
    return 0.0, "break failed"


def score_components(snap: Snapshot, p: Params = DEFAULT_PARAMS) -> list[Component]:
    """The item 12 table for one direction at one moment."""
    d = snap.direction
    price = float(snap.setup_row.close)
    atr_value = float(snap.setup_row.atr)

    ema_v, ema_note = _ema_value(snap.setup_row, d)
    rsi_v, rsi_note = _rsi_value(snap.setup_row, d, p)
    mfi_v, mfi_note = _mfi_value(snap.setup_row, d, p)
    macd_v, macd_note = _macd_value(snap.setup_row, d)
    sr_v, sr_note = _sr_value(price, snap.levels, atr_value, d, p)
    brk_v, brk_note = _breakout_value(snap.breakout, d)
    pa_v = pa.score(snap.entry_row, d, p)
    news_signed = snap.news_points * d

    return [
        Component("structure", p.w_structure, _structure_value(snap.setup_structure, d),
                  "HH+HL" if snap.setup_structure == BULLISH else "LH+LL"
                  if snap.setup_structure else "unclear"),
        Component("ema", p.w_ema, ema_v, ema_note),
        Component("rsi", p.w_rsi, rsi_v, rsi_note),
        Component("mfi", p.w_mfi, mfi_v, mfi_note),
        Component("macd", p.w_macd, macd_v, macd_note),
        Component("support/resistance", p.w_sr, sr_v, sr_note),
        Component("breakout/retest", p.w_breakout, brk_v, brk_note),
        Component("price action", p.w_price_action, pa_v,
                  ", ".join(pa.describe(snap.entry_row, d, p))),
        Component("correlation", p.w_correlation,
                  corr.correlation_score(d, snap.context.other_bias),
                  corr.describe(d, snap.context)),
        Component("dxy", p.w_dxy, corr.dxy_score(d, snap.context), ""),
        Component("news", p.w_news, ne.score_fraction(news_signed, p),
                  f"score {news_signed:+d}" if news_signed else "neutral"),
    ]


def total_score(components: list[Component]) -> float:
    return sum(c.points for c in components)


def grade_for(score: float, p: Params = DEFAULT_PARAMS) -> str:
    """Spec item 13. The grade is a label, not a probability — a score of 88
    does not mean 88% of these win."""
    if score >= p.score_a_plus:
        return A_PLUS
    if score >= p.score_very_strong:
        return VERY_STRONG
    if score >= p.score_strong:
        return STRONG
    if score >= p.score_min:
        return VALID
    if score >= p.score_watch:
        return WATCH
    return NO_TRADE


# --- stop loss and targets (spec items 16, 17, 18) --------------------------
def stop_for(snap: Snapshot, entry: float, p: Params = DEFAULT_PARAMS) -> tuple[float, str]:
    """Structure-based stop with an ATR buffer, never sitting on the level
    itself (spec item 16)."""
    atr_value = float(snap.setup_row.atr)
    buffer = p.sl_atr_buffer * atr_value
    anchor = nearest_below(snap.levels, entry) if snap.direction == 1 \
        else nearest_above(snap.levels, entry)
    if anchor is not None:
        stop = anchor.price - buffer if snap.direction == 1 else anchor.price + buffer
        note = f"beyond the {anchor.touches}-touch level at {anchor.price:.2f}"
    else:
        stop = entry - snap.direction * p.sl_min_atr * atr_value
        note = "ATR only, no structural level"
    # Floor: a stop tighter than this is noise on oil.
    minimum = p.sl_min_atr * atr_value
    if abs(entry - stop) < minimum:
        stop = entry - snap.direction * minimum
        note += f", widened to {p.sl_min_atr} ATR"
    return stop, note


def realistic_cap(snap: Snapshot, entry: float, risk: float,
                  p: Params = DEFAULT_PARAMS) -> tuple[float, str]:
    """How much RR the chart actually offers before the next major level.

    Spec item 17: never force 1:5 or 1:6 when the next level makes it
    unrealistic. The buffer keeps the target short of the level rather than
    inside it, because that is where price turns.
    """
    atr_value = float(snap.setup_row.atr)
    ahead = nearest_above(snap.levels, entry) if snap.direction == 1 \
        else nearest_below(snap.levels, entry)
    if ahead is None:
        return float(max(p.tp_rr)), "no level ahead"
    buffer = p.sl_atr_buffer * atr_value
    reachable = abs(ahead.price - entry) - buffer
    if risk <= 0:
        return 0.0, "no risk distance"
    return reachable / risk, f"next level {ahead.price:.2f}"


def targets_for(entry: float, risk: float, direction: int, rr_cap: float,
                score: float, p: Params = DEFAULT_PARAMS) -> list[tuple[float, float]]:
    """TP1..TP4 at item 18's ratios, kept inside both the realistic cap and the
    RR the score has earned (items 17, 37)."""
    allowed = min(rr_cap, p.rr_for_score(score))
    out = []
    for rr in p.tp_rr:
        if rr > allowed + 1e-9:
            break
        out.append((rr, entry + direction * rr * risk))
    return out


# --- the decision (spec items 14, 15, 37) ----------------------------------
def evaluate(snap: Snapshot, p: Params = DEFAULT_PARAMS) -> Signal | Rejection:
    """A signal, or the reason there is none."""
    d = snap.direction

    # Vetoes first — none of these can be outscored.
    if snap.setup_structure == UNCLEAR:
        return Rejection("30m structure unclear")
    if snap.setup_structure != d:
        return Rejection("30m structure is on the other side")
    # Item 14: never take the opposite side of the 1H trend.
    trend = snap.trend_structure or ema_bias(snap.trend_row)
    if trend == -d:
        return Rejection("1h trend is against this direction")
    if trend == UNCLEAR:
        return Rejection("1h trend unclear")
    if pa.is_dead(snap.entry_row, p):
        return Rejection("15m entry candle is dead")

    blackout = ne.blocking_event(snap.news, snap.when, p)
    if blackout is not None:
        return Rejection(f"news blackout: {blackout.title}")
    if ne.contradicts(snap.news_points, d, p):
        return Rejection(f"news contradicts (score {snap.news_points:+d})")

    context_veto = corr.veto(d, snap.context)
    if context_veto:
        return Rejection(context_veto)

    atr_value = float(snap.setup_row.atr)
    if not (p.atr_pct_min <= float(snap.setup_row.atr_pct) <= p.atr_pct_max):
        return Rejection(f"volatility out of range ({float(snap.setup_row.atr_pct):.2f}% ATR)")
    if float(snap.setup_row.adx) < p.adx_trending:
        return Rejection(f"ranging market (ADX {float(snap.setup_row.adx):.0f})")

    price = float(snap.entry_row.close)
    in_the_way = blocked(d, price, snap.levels, atr_value, p)
    if in_the_way is not None:
        return Rejection(f"level in the way at {in_the_way.price:.2f}")

    # Plan the trade before scoring it: item 17 refuses anything under 1:2
    # however good it looks.
    half_zone = p.entry_zone_atr * atr_value
    entry_low, entry_high = price - half_zone, price + half_zone
    entry = entry_high if d == 1 else entry_low
    stop, stop_note = stop_for(snap, entry, p)
    risk = abs(entry - stop)
    if risk <= 0:
        return Rejection("stop collapsed onto the entry")
    rr_cap, cap_note = realistic_cap(snap, entry, risk, p)
    if rr_cap < p.rr_min:
        return Rejection(f"no realistic 1:{p.rr_min:.0f} — only {rr_cap:.1f} to {cap_note}")

    components = score_components(snap, p)
    score = total_score(components)
    grade = grade_for(score, p)
    if score < p.score_min:
        return Rejection(f"score {score:.0f} below {p.score_min:.0f}", score, components, grade)

    tps = targets_for(entry, risk, d, rr_cap, score, p)
    if not tps:
        return Rejection(f"no target fits inside {rr_cap:.1f} RR", score, components, grade)

    return Signal(
        symbol=snap.symbol, direction=d, when=snap.when,
        entry_low=entry_low, entry_high=entry_high, sl=stop, tps=tps,
        score=score, grade=grade, rr_cap=rr_cap, components=components,
        notes=[stop_note, cap_note],
    )
