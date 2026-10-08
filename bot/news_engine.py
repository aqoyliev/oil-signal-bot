"""Economic events, the trading blackout and the news score (spec items 9-11).

The honest constraint up front, because it decides the design:

The free calendar feed carries **this week only** — every historical range
returns 404. So a feed-driven blackout could not be replayed over the years of
history spec items 29/30 demand, and a rule that cannot be measured must not
quietly shape the score (item 39).

The split is therefore:

  * `ScheduledCalendar` generates the recurring releases from their publication
    rules, which are reconstructible for any past or future date. This is what
    the backtest uses, so the blackout it measures is the blackout the bot runs.
  * `ForexFactoryCalendar` adds the current week's richer detail — impact,
    forecast, previous — for live use.
  * Irregular events (FOMC, CPI, OPEC meetings) follow no formula. They load
    from `data/events.json` when it exists; without that file they are simply
    absent, and the backtest report says so rather than pretending otherwise.

The -3..+3 news score of item 11 needs actual-versus-expected. Historical
consensus is not freely available, so the score is NEUTRAL unless a live
provider supplies both numbers. Item 11 already says news only confirms and
never generates a trade, so a neutral default costs nothing but honesty.
"""
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Params, DEFAULT_PARAMS

ET = ZoneInfo("America/New_York")
OIL, MACRO = "oil", "macro"
HIGH, MEDIUM, LOW = "high", "medium", "low"

NEUTRAL_SCORE = 0


@dataclass(frozen=True)
class Event:
    time: datetime            # tz-aware, UTC
    title: str
    kind: str                 # OIL or MACRO
    impact: str               # HIGH / MEDIUM / LOW
    forecast: float | None = None
    previous: float | None = None
    actual: float | None = None
    bullish_when_above: bool = False   # how a surprise maps to oil direction

    @property
    def surprise(self) -> float | None:
        """Actual minus forecast, or None when either is missing."""
        if self.actual is None or self.forecast is None:
            return None
        return self.actual - self.forecast


class CalendarProvider(ABC):
    @abstractmethod
    def events(self, start: datetime, end: datetime) -> list[Event]:
        """Events in [start, end), sorted by time."""


# --- US federal holidays that push the EIA report back a day -----------------
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month, 1) + timedelta(days=31)
    d = date(d.year, d.month, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def us_holidays(year: int) -> set[date]:
    """The federal holidays that matter for release schedules."""
    return {
        date(year, 1, 1),                        # New Year's Day
        _nth_weekday(year, 1, 0, 3),             # MLK Day
        _nth_weekday(year, 2, 0, 3),             # Presidents' Day
        _last_weekday(year, 5, 0),               # Memorial Day
        date(year, 6, 19),                       # Juneteenth
        date(year, 7, 4),                        # Independence Day
        _nth_weekday(year, 9, 0, 1),             # Labor Day
        _nth_weekday(year, 11, 3, 4),            # Thanksgiving
        date(year, 12, 25),                      # Christmas
    }


class ScheduledCalendar(CalendarProvider):
    """Recurring releases derived from their publication rules.

    Covered, and reconstructible for any date:
      * EIA Weekly Petroleum Status Report — Wednesday 10:30 ET, pushed to
        Thursday when a federal holiday falls earlier in the same week
      * API Statistical Bulletin — Tuesday 16:30 ET
      * US Non-Farm Payrolls — first Friday of the month, 08:30 ET

    Not covered, because they follow no formula: FOMC, CPI, OPEC meetings.
    Those come from `extra_events` / `data/events.json`.
    """

    def __init__(self, extra: list[Event] | None = None):
        self.extra = sorted(extra or [], key=lambda e: e.time)

    def events(self, start: datetime, end: datetime) -> list[Event]:
        out: list[Event] = []
        day = start.astimezone(ET).date() - timedelta(days=1)
        last = end.astimezone(ET).date() + timedelta(days=1)
        while day <= last:
            out.extend(self._for_day(day))
            day += timedelta(days=1)
        out.extend(e for e in self.extra if start <= e.time < end)
        out = [e for e in out if start <= e.time < end]
        return sorted(out, key=lambda e: e.time)

    def _for_day(self, day: date) -> list[Event]:
        found: list[Event] = []
        holidays = us_holidays(day.year)
        if day in holidays:
            return found

        # EIA inventories: Wednesday, or Thursday after an earlier holiday.
        monday = day - timedelta(days=day.weekday())
        shifted = any((monday + timedelta(days=i)) in holidays for i in range(3))
        eia_weekday = 3 if shifted else 2
        if day.weekday() == eia_weekday:
            found.append(Event(_at(day, time(10, 30)), "EIA Crude Oil Inventories",
                               OIL, HIGH, bullish_when_above=False))
        if day.weekday() == 1:
            found.append(Event(_at(day, time(16, 30)), "API Crude Oil Inventories",
                               OIL, MEDIUM, bullish_when_above=False))
        # Non-farm payrolls: first Friday of the month.
        if day.weekday() == 4 and day.day <= 7:
            found.append(Event(_at(day, time(8, 30)), "US Non-Farm Payrolls",
                               MACRO, HIGH))
        return found


def _at(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock, tzinfo=ET).astimezone(timezone.utc)


def load_extra_events(path: str | Path | None = None) -> list[Event]:
    """Irregular events from JSON: [{"time": ISO8601, "title": ..., "kind":
    "oil"|"macro", "impact": "high"|...}]. Missing file means no extras."""
    path = Path(path or Path(__file__).resolve().parent.parent / "data" / "events.json")
    if not path.exists():
        logging.info(f"no irregular-event file at {path}; FOMC/CPI/OPEC not covered")
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for item in raw:
        when = datetime.fromisoformat(item["time"])
        if when.tzinfo is None:
            raise ValueError(f"event {item['title']!r} has no timezone")
        out.append(Event(when.astimezone(timezone.utc), item["title"],
                         item.get("kind", MACRO), item.get("impact", HIGH)))
    return out


class ForexFactoryCalendar(CalendarProvider):
    """The current week with impact, forecast and previous — live use only.

    Fetching is the caller's job (`feed` is the parsed JSON), so this module
    stays testable without network access.
    """
    URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    OIL_WORDS = ("oil", "crude", "opec", "rig count", "gasoline", "distillate")
    MACRO_COUNTRIES = ("USD",)

    def __init__(self, feed: list[dict]):
        self.feed = feed

    def events(self, start: datetime, end: datetime) -> list[Event]:
        out = []
        for row in self.feed:
            when = datetime.fromisoformat(row["date"]).astimezone(timezone.utc)
            if not (start <= when < end):
                continue
            title = row.get("title", "")
            is_oil = any(w in title.lower() for w in self.OIL_WORDS)
            if not is_oil and row.get("country") not in self.MACRO_COUNTRIES:
                continue
            out.append(Event(
                time=when, title=title, kind=OIL if is_oil else MACRO,
                impact=str(row.get("impact", LOW)).lower(),
                forecast=_number(row.get("forecast")),
                previous=_number(row.get("previous")),
                bullish_when_above=not is_oil,
            ))
        return sorted(out, key=lambda e: e.time)


def _number(raw) -> float | None:
    """Calendar figures arrive as '1.9M', '-2.3%', '' — keep the magnitude."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    scale = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(text[-1].upper())
    if scale:
        text = text[:-1]
    try:
        return float(text) * (scale or 1.0)
    except ValueError:
        return None


# --- blackout (spec item 10) ------------------------------------------------
def blocking_event(events: list[Event], when: datetime,
                   p: Params = DEFAULT_PARAMS) -> Event | None:
    """The event that forbids opening a trade at `when`, if any.

    Item 10: nothing new in the minutes before a major release, and nothing in
    the first minutes after it either — the initial spike is not a signal.
    Only HIGH impact events block; medium ones only cost score.
    """
    before = timedelta(minutes=p.blackout_before_min)
    after = timedelta(minutes=p.blackout_after_min)
    for event in events:
        if event.impact != HIGH:
            continue
        if event.time - before <= when <= event.time + after:
            return event
    return None


def next_event(events: list[Event], when: datetime) -> Event | None:
    upcoming = [e for e in events if e.time > when]
    return upcoming[0] if upcoming else None


# --- news score (spec item 11) ---------------------------------------------
def event_score(event: Event, p: Params = DEFAULT_PARAMS) -> int:
    """-3..+3 for one event, or NEUTRAL when the actual is not known.

    For inventories a *draw* (actual below forecast) is bullish for oil, which
    is why `bullish_when_above` is False on them. The magnitude is graded
    against the forecast, so a 0.2M miss is not treated like a 5M shock.
    """
    surprise = event.surprise
    if surprise is None:
        return NEUTRAL_SCORE
    direction = 1 if event.bullish_when_above else -1
    scale = max(abs(event.forecast or 0.0), 1.0)
    magnitude = abs(surprise) / scale
    steps = 3 if magnitude >= 1.0 else 2 if magnitude >= 0.5 else 1 if magnitude >= 0.2 else 0
    sign = 1 if surprise > 0 else -1
    return max(-p.news_score_max, min(p.news_score_max, steps * sign * direction))


def news_score(events: list[Event], when: datetime, window_hours: float = 12.0,
               p: Params = DEFAULT_PARAMS) -> int:
    """Combined -3..+3 over the events already released in the recent window."""
    since = when - timedelta(hours=window_hours)
    scores = [event_score(e, p) for e in events
              if since <= e.time <= when and e.surprise is not None]
    if not scores:
        return NEUTRAL_SCORE
    total = sum(scores)
    return max(-p.news_score_max, min(p.news_score_max, total))


def score_fraction(score: int, p: Params = DEFAULT_PARAMS) -> float:
    """Map -3..+3 onto the 0..1 the scoring engine wants, for a given side.

    Caller passes the score already signed for its direction. Neutral is 0.5,
    so an unknown news state neither rewards nor punishes a setup.
    """
    return (score + p.news_score_max) / (2 * p.news_score_max)


def contradicts(score: int, direction: int, p: Params = DEFAULT_PARAMS) -> bool:
    """True when the news is contradictory enough to refuse the trade (item 11
    is confirmation-only, so this needs the score to be clearly against)."""
    return score * direction <= p.news_veto
