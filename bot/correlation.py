"""WTI/Brent agreement and the dollar (spec items 7, 8).

Both are *context*: they adjust a setup's score and, in one specific
combination, veto it. Neither produces a direction of its own — item 8 is
explicit that the dollar must not override oil's own price action.

The asymmetry worth noting: oil-vs-oil disagreement is a strong warning
(the two grades normally move together, so a split usually means one of the
reads is wrong), while the dollar is a background force that is often simply
irrelevant on a 30-minute setup.
"""
from dataclasses import dataclass

from .config import Params, DEFAULT_PARAMS
from .indicators import ema_bias
from .market_structure import BULLISH, UNCLEAR

AGREE, NEUTRAL, CONFLICT = 1, 0, -1


@dataclass(frozen=True)
class Context:
    """Everything outside the traded instrument that the score cares about."""
    other_bias: int          # the other grade's bias: BULLISH / BEARISH / UNCLEAR
    dxy_bias: int            # 1 = dollar strengthening, -1 weakening, 0 flat
    dxy_strong: bool         # the move is big enough to matter


def instrument_bias(row, structure: int) -> int:
    """One read per instrument, from the EMA stack and the structure.

    Used for both grades so the comparison in item 7 is like-for-like. When the
    two inputs disagree the bias is UNCLEAR rather than a coin flip.
    """
    trend = ema_bias(row)
    if trend == UNCLEAR or structure == UNCLEAR:
        return trend or structure
    return trend if trend == structure else UNCLEAR


def oil_agreement(direction: int, other_bias: int) -> int:
    """AGREE, NEUTRAL or CONFLICT between the two grades (spec item 7)."""
    if other_bias == UNCLEAR:
        return NEUTRAL
    return AGREE if other_bias == direction else CONFLICT


def correlation_score(direction: int, other_bias: int) -> float:
    """0.0 to 1.0 for the five correlation points of spec item 12.

    Item 7 warns against demanding perfect correlation, because the grades do
    diverge temporarily — so NEUTRAL still earns half the points rather than
    none.
    """
    state = oil_agreement(direction, other_bias)
    return {AGREE: 1.0, NEUTRAL: 0.5, CONFLICT: 0.0}[state]


def dxy_bias_from(row, p: Params = DEFAULT_PARAMS) -> tuple[int, bool]:
    """(direction, strong) for the dollar index.

    Direction comes from the EMA stack, strength from how far price sits from
    the mid EMA in ATR terms — a dollar drifting sideways above its EMAs is not
    the same input as one breaking out.
    """
    bias = ema_bias(row)
    if bias == UNCLEAR:
        return UNCLEAR, False
    distance = abs(float(row.close) - float(row.ema_mid)) / max(float(row.atr), 1e-9)
    return bias, distance >= p.dxy_strong_atr


def dollar_against(direction: int, ctx: Context) -> bool:
    """Is the dollar a headwind for this trade? (spec item 8)

    A strengthening dollar pressures oil down, so it opposes a BUY; a weakening
    dollar supports oil, so it opposes a SELL. In both cases the dollar's own
    direction equals the oil direction it fights.
    """
    return ctx.dxy_bias != UNCLEAR and ctx.dxy_bias == direction


def dxy_score(direction: int, ctx: Context) -> float:
    """0.0 to 1.0 for the five dollar points of spec item 12.

    The worst case still scores above zero when the dollar move is weak,
    because item 8 says a mildly contradictory dollar only "reduces the score
    slightly" rather than killing the setup.
    """
    if ctx.dxy_bias == UNCLEAR:
        return 0.5
    if dollar_against(direction, ctx):
        return 0.0 if ctx.dxy_strong else 0.4
    return 1.0 if ctx.dxy_strong else 0.75


def veto(direction: int, ctx: Context) -> str | None:
    """The one combination spec item 8 says to sit out, or None.

    "Oil technical structure = BUY, DXY strongly bullish, WTI/Brent divergence
    -> preferably WAIT." All three have to line up; a strong dollar on its own
    only costs points, because the dollar may not override oil's price action.
    """
    if ctx.dxy_strong and dollar_against(direction, ctx) \
            and oil_agreement(direction, ctx.other_bias) == CONFLICT:
        return "dollar strongly against and the two grades disagree"
    return None


def describe(direction: int, ctx: Context) -> str:
    """One line for the signal message and the log."""
    state = {AGREE: "confirms", NEUTRAL: "neutral", CONFLICT: "disagrees"}[
        oil_agreement(direction, ctx.other_bias)]
    if ctx.dxy_bias == UNCLEAR:
        dollar = "flat"
    else:
        word = "up" if ctx.dxy_bias == BULLISH else "down"
        dollar = f"{word}{' strongly' if ctx.dxy_strong else ''}"
    return f"other grade {state}, dollar {dollar}"
