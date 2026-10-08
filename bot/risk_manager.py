"""Frequency, duplicates and risk control (spec items 20, 21, 24, 25, 26).

Two jobs, both stateful, which is why they are not in `signal_engine`:

  * `SignalGate` decides whether an already-valid signal may actually be sent.
    A score says a setup is good; it does not say the bot should fire again on
    the next 15-minute candle of the same breakout. Item 21 asks for exactly
    this, and without it a single setup produces a dozen alerts.
  * `RiskManager` turns a signal into a position size from the account balance,
    the risk percentage and the stop distance (item 26), and stops the day once
    the daily loss limit is reached (item 24).

On item 25 there is nothing to implement and that is the point: no method here
takes a previous loss as input. Size depends on balance, risk percent and stop
distance, and on nothing else. There is no path through this module by which a
loss can increase the next position.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import contracts
from .config import Params, DEFAULT_PARAMS, TZ
from .signal_engine import Signal


def _day(when: datetime, tz: str = TZ) -> date:
    """The trading day a moment belongs to, in the user's timezone (item 24's
    limit resets per day, and the user reads days in local time)."""
    return when.astimezone(ZoneInfo(tz)).date()


@dataclass
class SignalGate:
    """Items 20 and 21: how often the bot is allowed to speak."""
    p: Params = DEFAULT_PARAMS
    tz: str = TZ
    _sent_on: dict = field(default_factory=dict)      # day -> count
    _last_bar: dict = field(default_factory=dict)     # (symbol, dir) -> bar number
    _last_basis: dict = field(default_factory=dict)   # (symbol, dir) -> Signal.basis

    # Identity comes from Signal.basis: the broken level and the moment it
    # broke. That is what item 21 means by "new setup / new breakout" — the
    # same break retested on three consecutive candles is one opportunity.

    def admit(self, signal: Signal, bar: int, basis: tuple | None = None) -> str | None:
        """None if the signal may be sent, otherwise why it may not."""
        day = _day(signal.when, self.tz)
        if self._sent_on.get(day, 0) >= self.p.max_signals_per_day:
            return f"daily signal limit reached ({self.p.max_signals_per_day})"

        key = (signal.symbol, signal.direction)
        identity = basis if basis is not None else signal.basis
        if self._last_basis.get(key) == identity:
            return "same setup already signalled"

        last = self._last_bar.get(key)
        if last is not None and bar - last < self.p.cooldown_bars:
            return f"cooldown ({bar - last} of {self.p.cooldown_bars} bars)"
        return None

    def record(self, signal: Signal, bar: int, basis: tuple | None = None):
        """Call only after the signal was actually sent."""
        day = _day(signal.when, self.tz)
        self._sent_on[day] = self._sent_on.get(day, 0) + 1
        key = (signal.symbol, signal.direction)
        self._last_bar[key] = bar
        self._last_basis[key] = basis if basis is not None else signal.basis

    def sent_today(self, when: datetime) -> int:
        return self._sent_on.get(_day(when, self.tz), 0)


@dataclass
class Position:
    """A sized trade, with the figure that was actually risked."""
    symbol: str
    lots: float
    risk_amount: float        # intended
    actual_risk: float        # after rounding down onto the lot step
    sl_distance: float
    note: str = ""

    @property
    def tradable(self) -> bool:
        return self.lots > 0


@dataclass
class RiskManager:
    """Items 24, 25, 26: size from risk, and stop for the day when told to."""
    balance: float
    p: Params = DEFAULT_PARAMS
    tz: str = TZ
    _realised: dict = field(default_factory=dict)     # day -> pnl in currency

    def size(self, signal: Signal) -> Position:
        """Position size from balance, risk percent and stop distance.

        Nothing about past trades enters this calculation (item 25). When the
        contract's minimum lot cannot express the allowed risk, the result is
        zero lots, which the caller must read as "no trade" rather than
        rounding up into a larger risk than the rules permit.
        """
        contract = contracts.get(signal.symbol)
        sl_distance = signal.risk
        risk_amount = self.balance * self.p.risk_per_trade / 100.0
        lots = contract.lots_for_risk(risk_amount, sl_distance)
        actual = contract.risk_for_lots(lots, sl_distance)
        note = ""
        if lots == 0.0:
            needed = contract.min_balance_for(self.p.risk_per_trade, sl_distance)
            note = (f"minimum lot risks {contract.min_risk(sl_distance):.2f}, "
                    f"over {self.p.risk_per_trade}% of {self.balance:.0f} — "
                    f"needs a balance of {needed:.0f}")
        elif not contract.confirmed:
            note = "contract size not yet confirmed from the terminal"
        return Position(signal.symbol, lots, risk_amount, actual, sl_distance, note)

    # --- daily loss limit (item 24) ---
    def record_result(self, when: datetime, pnl: float):
        day = _day(when, self.tz)
        self._realised[day] = self._realised.get(day, 0.0) + pnl

    def realised(self, when: datetime) -> float:
        return self._realised.get(_day(when, self.tz), 0.0)

    def day_blocked(self, when: datetime) -> str | None:
        """Item 24: once the daily loss limit is hit, no more signals today."""
        limit = self.balance * self.p.max_daily_loss / 100.0
        lost = -self.realised(when)
        if lost >= limit:
            return f"daily loss limit reached ({lost:.2f} of {limit:.2f})"
        return None
