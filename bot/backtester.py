"""Trade simulation and metrics (spec items 29, 30, 39).

This is the module item 39 rests on: "what percentage of historical setups with
this exact configuration actually won?" Everything here exists to answer that
without flattering it.

The modelling choices, all deliberately pessimistic where the data cannot say:

  * **Spread is paid once per round trip.** The feed is the bid side, so stops
    and targets are checked against bid prices and the ask-bid spread is
    subtracted from the result. On a 1:2 trade a $0.05 spread against a $1.00
    stop is 5% of the risk, which is not negligible.
  * **Within a bar the stop is checked first.** A 15-minute candle that touched
    both the stop and the target is scored as a loss, because the tick order is
    unknown and assuming the good one is how backtests lie.
  * **One position per symbol.** A signal arriving while a trade is open is
    skipped rather than stacked, which is what a single account can actually do.
  * **Entry is a market fill at the zone's far edge**, so the risk is never
    understated.
  * Results are in **R multiples** (profit divided by the money risked), which
    is comparable across instruments and price levels. Currency figures follow
    from R and the risk percentage.

Item 30's train/test split is `split()`. Optimising on everything and quoting
the same numbers back is the failure it exists to prevent.
"""
import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import news_engine as ne
from . import risk_manager as rm
from . import scanner
from . import signal_engine as se
from .config import Params, DEFAULT_PARAMS
from .data_provider import TIMEFRAMES
from .scanner import Frames

STOP, TARGET, TRAIL, TIMEOUT, OPEN = "stop", "target", "trail", "timeout", "open"


@dataclass
class Trade:
    symbol: str
    direction: int
    entry_time: pd.Timestamp
    entry: float
    sl: float
    risk: float
    score: float
    grade: str
    planned_rr: float
    exit_time: pd.Timestamp | None = None
    r: float = 0.0                 # realised, net of spread
    reason: str = OPEN
    tps_hit: int = 0
    best_rr: float = 0.0           # how far it ran, whether or not it was banked
    bars: int = 0
    # The item 12 table that produced this trade, kept so each component's
    # predictive value can be measured on its own (item 31 asks for the weights
    # to be optimised; first they have to be shown to carry any signal).
    components: list = field(default_factory=list)

    @property
    def won(self) -> bool:
        return self.r > 0


def hold_bars(p: Params) -> int:
    """The time stop in bars of the entry timeframe."""
    hours = TIMEFRAMES[p.entry_tf].total_seconds() / 3600.0
    return max(1, int(round(p.max_hold_hours / hours)))


def simulate(signal: se.Signal, bars: pd.DataFrame, spread: float,
             p: Params = DEFAULT_PARAMS) -> Trade:
    """Walk one signal forward over `bars` (15m, starting after the signal).

    Partial targets per item 18, break-even after TP1 and an ATR trail after
    TP2 per item 19.
    """
    d = signal.direction
    entry = signal.entry_price
    risk = signal.risk
    trade = Trade(signal.symbol, d, signal.when, entry, signal.sl, risk,
                  signal.score, signal.grade,
                  signal.tps[-1][0] if signal.tps else 0.0,
                  components=list(signal.components))

    stop = signal.sl
    remaining = 1.0
    banked = 0.0            # in R, before spread
    next_tp = 0
    # Item 18 splits the position over four targets, but the realistic cap of
    # item 17 often leaves only one or two. Keeping a literal 25% per target
    # would strand the rest of the position with no target at all — measured,
    # that was 75% of the position on half the signals, riding to the time stop.
    # The shares are therefore spread over the targets that exist.
    weights = list(p.tp_share[:len(signal.tps)]) or [1.0]
    scale = sum(weights) or 1.0
    shares = [w / scale for w in weights]

    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    closes = bars["close"].to_numpy()
    atrs = bars["atr"].to_numpy()

    for i in range(len(bars)):
        trade.bars = i + 1
        high, low = float(highs[i]), float(lows[i])
        excursion = (high - entry) / risk if d == 1 else (entry - low) / risk
        trade.best_rr = max(trade.best_rr, excursion)

        # Stop first — see the module docstring.
        hit_stop = low <= stop if d == 1 else high >= stop
        if hit_stop:
            realised = (stop - entry) * d / risk
            banked += remaining * realised
            trade.exit_time = bars.index[i]
            trade.reason = TRAIL if trade.tps_hit >= p.trail_after_tp else STOP
            remaining = 0.0
            break

        # Then targets, in order, possibly several in one bar.
        while next_tp < len(signal.tps):
            rr, price = signal.tps[next_tp]
            reached = high >= price if d == 1 else low <= price
            if not reached:
                break
            share = shares[next_tp] if next_tp < len(shares) else remaining
            share = min(share, remaining)
            banked += share * rr
            remaining -= share
            next_tp += 1
            trade.tps_hit += 1
            if trade.tps_hit >= p.breakeven_after_tp:
                stop = entry            # item 18: break-even after TP1
            if remaining <= 1e-9:
                trade.exit_time = bars.index[i]
                trade.reason = TARGET
                break
        if remaining <= 1e-9:
            break

        # Trailing stop once enough is banked (item 19) — loose, because oil
        # swings intraday and a tight trail just donates the runner back.
        if trade.tps_hit >= p.trail_after_tp:
            room = p.trail_atr * float(atrs[i])
            stop = max(stop, high - room) if d == 1 else min(stop, low + room)

        if i + 1 >= hold_bars(p):
            close = float(closes[i])
            banked += remaining * (close - entry) * d / risk
            trade.exit_time = bars.index[i]
            trade.reason = TIMEOUT
            remaining = 0.0
            break

    if remaining > 1e-9:
        close = float(closes[-1]) if len(closes) else entry
        banked += remaining * (close - entry) * d / risk
        trade.exit_time = bars.index[-1] if len(bars) else signal.when
        trade.reason = OPEN

    # One spread per round trip, expressed in R.
    trade.r = banked - spread / risk
    return trade


def run(frames: Frames, other: Frames | None, dxy: pd.DataFrame | None,
        events: list[ne.Event], spread: float,
        p: Params = DEFAULT_PARAMS, since: pd.Timestamp | None = None) -> list[Trade]:
    """Scan, gate and simulate — the whole pipeline the live bot runs.

    `since` drops signals from the warmup history the frames carry before the
    test window, so the measured period is the one that was asked for.
    """
    merged = scanner.align(frames, other, dxy, p)
    gate = rm.SignalGate(p)
    entry_index = frames.entry.index
    trades: list[Trade] = []
    busy_until: pd.Timestamp | None = None

    for bar, (when, _direction, out) in enumerate(scanner.scan(frames, merged, events, p)):
        if not isinstance(out, se.Signal):
            continue
        if since is not None and when < since:
            continue
        if busy_until is not None and when <= busy_until:
            continue                      # one position per symbol
        if gate.admit(out, bar // 2) is not None:
            continue
        gate.record(out, bar // 2)

        start = int(entry_index.searchsorted(when, side="right"))
        forward = frames.entry.iloc[start:start + hold_bars(p)]
        if forward.empty:
            continue
        trade = simulate(out, forward, spread, p)
        trades.append(trade)
        busy_until = trade.exit_time
    return trades


# --- metrics (spec item 29) -------------------------------------------------
@dataclass
class Report:
    trades: int = 0
    wins: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    net_r: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    expectancy_r: float = 0.0
    max_drawdown_r: float = 0.0
    sharpe: float = 0.0
    avg_rr_achieved: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    reasons: dict = field(default_factory=dict)

    def as_row(self) -> str:
        return (f"{self.trades:>6} {self.win_rate:>7.1f}% {self.profit_factor:>7.2f} "
                f"{self.net_r:>+9.1f} {self.expectancy_r:>+9.3f} {self.max_drawdown_r:>8.1f} "
                f"{self.sharpe:>7.2f} {self.max_consecutive_losses:>5}")

    @staticmethod
    def header() -> str:
        return (f"{'trades':>6} {'win':>8} {'PF':>7} {'net R':>9} "
                f"{'exp/trade':>9} {'maxDD':>8} {'sharpe':>7} {'maxL':>5}")


def report(trades: list[Trade]) -> Report:
    """Every figure item 29 asks for, computed in R."""
    out = Report(trades=len(trades))
    if not trades:
        return out
    rs = np.array([t.r for t in trades], dtype=float)
    wins, losses = rs[rs > 0], rs[rs <= 0]
    out.wins = int(len(wins))
    out.win_rate = 100.0 * len(wins) / len(rs)
    gross_win, gross_loss = float(wins.sum()), float(-losses.sum())
    out.profit_factor = gross_win / gross_loss if gross_loss > 0 else math.inf
    out.net_r = float(rs.sum())
    out.avg_win_r = float(wins.mean()) if len(wins) else 0.0
    out.avg_loss_r = float(losses.mean()) if len(losses) else 0.0
    out.expectancy_r = float(rs.mean())
    equity = rs.cumsum()
    out.max_drawdown_r = float(np.max(np.maximum.accumulate(equity) - equity)) if len(equity) else 0.0
    # Per-trade Sharpe: mean over standard deviation. Not annualised — the
    # trade count is too small for that to mean anything.
    out.sharpe = float(rs.mean() / rs.std(ddof=1)) if len(rs) > 1 and rs.std(ddof=1) > 0 else 0.0
    out.avg_rr_achieved = float(np.mean([t.best_rr for t in trades]))
    out.max_consecutive_wins = _streak(rs > 0)
    out.max_consecutive_losses = _streak(rs <= 0)
    counts: dict = {}
    for t in trades:
        counts[t.reason] = counts.get(t.reason, 0) + 1
    out.reasons = counts
    return out


def _streak(flags) -> int:
    best = run_len = 0
    for flag in flags:
        run_len = run_len + 1 if flag else 0
        best = max(best, run_len)
    return best


def split(trades: list[Trade], train_fraction: float = 0.7):
    """Item 30: the first 70% of trades to fit on, the last 30% to check.

    Split by trade order rather than by date so both halves hold a comparable
    number of trades; a calendar split can put most of the activity on one side.
    """
    cut = int(len(trades) * train_fraction)
    return trades[:cut], trades[cut:]


def rr_variants(p: Params = DEFAULT_PARAMS) -> dict:
    """Item 29 asks for 1:2 through 1:6 tested separately — single-target
    configurations, so each ratio is measured on its own rather than blended
    into the partial ladder."""
    out = {}
    for rr in (2.0, 3.0, 4.0, 5.0, 6.0):
        out[f"1:{rr:.0f}"] = replace(
            p, tp_rr=(rr,), tp_share=(1.0,),
            rr_by_score=((p.score_min, rr),),
            breakeven_after_tp=99, trail_after_tp=99)   # pure fixed-target test
    return out
