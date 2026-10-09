"""Market data behind a replaceable interface (spec item 32).

Nothing above this module knows where candles come from. `DataProvider` is the
contract; `DukascopyProvider` is the current implementation, chosen because it
is the only free source with deep intraday history for oil:

  * 15m / 30m / 1h candles back to 2013 for WTI, Brent and the dollar index
  * bid *and* ask, so the backtester pays the real spread instead of guessing
  * CFD prices, which is what the trader actually deals at

Yahoo Finance, used by the previous version, caps intraday history at 60 days
and has no ask side, which makes the backtest the spec demands impossible.

Every failure raises `MarketDataError`. Callers must treat that as "no trade"
(spec item 34) and never fall back to stale or partial candles.
"""
import logging
import pickle
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from . import config

COLUMNS = ["open", "high", "low", "close", "volume"]
BID, ASK = "bid", "ask"

# Candle length per timeframe, used to drop the still-forming candle.
TIMEFRAMES = {
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


# A higher timeframe can be rebuilt from a lower one, bar for bar: resampling
# 1h into 4h was compared against Dukascopy's own 4h series over six months of
# WTI and Brent and matched every boundary and every price exactly. That makes
# it safe to fill a hole in the sparser feed with real data from the denser one.
DERIVE_FROM = {"4h": "1h", "1d": "1h"}

# The longest legitimate break in oil trading is the weekend, extended by a
# holiday: 3 days 8 hours is the longest observed over four years. Anything
# longer is a hole in the feed, not a closed market.
MAX_MARKET_CLOSURE = timedelta(days=4)


class MarketDataError(Exception):
    """Data is missing, stale or malformed — the caller must not trade."""


class DataProvider(ABC):
    """Implement this to swap the data source (spec item 32)."""

    @abstractmethod
    def candles(self, symbol: str, timeframe: str, start: datetime, end: datetime,
                side: str = BID) -> pd.DataFrame:
        """OHLCV with a UTC DatetimeIndex and the `COLUMNS` columns.

        The index is the candle's *open* time. Raises `MarketDataError` if the
        range cannot be served.
        """

    def closed_candles(self, symbol: str, timeframe: str, start: datetime, end: datetime,
                       side: str = BID) -> pd.DataFrame:
        """Same, minus the candle that is still forming — decisions use only
        closed candles, otherwise a signal repaints."""
        df = self.candles(symbol, timeframe, start, end, side)
        length = TIMEFRAMES[timeframe]
        return df[df.index + length <= datetime.now(timezone.utc)]

    def spread(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.Series:
        """Ask minus bid per candle, in price units — the real cost per trade."""
        ask = self.candles(symbol, timeframe, start, end, ASK)
        bid = self.candles(symbol, timeframe, start, end, BID)
        return (ask["close"] - bid["close"]).dropna()


class DukascopyProvider(DataProvider):
    """Dukascopy's free historical feed, cached on disk by calendar month.

    A single 15m request for several years is slow and easy to hit limits with,
    so ranges are fetched one month at a time and pickled. Only the month that
    contains `now` is refetched; closed months are read from the cache.
    """

    SYMBOLS = {
        "WTI": "INSTRUMENT_CMD_ENERGY_E_LIGHT",      # USOIL / WTI CFD
        "BRENT": "INSTRUMENT_CMD_ENERGY_E_BRENT",    # UKOIL / Brent CFD
        "DXY": "INSTRUMENT_IDX_AMERICA_DOLLAR_IDX_USD",
    }
    INTERVALS = {
        "15m": "INTERVAL_MIN_15",
        "30m": "INTERVAL_MIN_30",
        "1h": "INTERVAL_HOUR_1",
        "4h": "INTERVAL_HOUR_4",
        "1d": "INTERVAL_DAY_1",
    }

    def __init__(self, cache_dir: str | Path | None = None):
        self.cache = Path(cache_dir or config.CACHE_DIR
                          or Path(__file__).resolve().parent.parent / "data" / "candles")
        self.cache.mkdir(parents=True, exist_ok=True)

    # --- the Dukascopy package is imported lazily so importing this module
    #     (and therefore the whole bot) does not depend on it being installed ---
    @staticmethod
    def _api():
        try:
            import dukascopy_python
            from dukascopy_python import instruments
        except ImportError as err:  # pragma: no cover - environment problem
            raise MarketDataError(f"dukascopy_python is not installed: {err}") from err
        return dukascopy_python, instruments

    def _resolve(self, symbol: str, timeframe: str, side: str):
        if symbol not in self.SYMBOLS:
            raise MarketDataError(f"unknown symbol {symbol!r}")
        if timeframe not in self.INTERVALS:
            raise MarketDataError(f"unknown timeframe {timeframe!r}")
        if side not in (BID, ASK):
            raise MarketDataError(f"unknown side {side!r}")
        api, instruments = self._api()
        return (api,
                getattr(instruments, self.SYMBOLS[symbol]),
                getattr(api, self.INTERVALS[timeframe]),
                getattr(api, f"OFFER_SIDE_{side.upper()}"))

    def _month(self, symbol: str, timeframe: str, side: str, year: int, month: int) -> pd.DataFrame:
        """One calendar month of candles, from the cache when it is complete."""
        path = self.cache / f"{symbol}_{timeframe}_{side}_{year}{month:02d}.pkl"
        now = datetime.now(timezone.utc)
        # The running month keeps changing, so never trust its cache.
        complete = (year, month) != (now.year, now.month)
        if complete and path.exists():
            return pickle.loads(path.read_bytes())

        api, instrument, interval, offer = self._resolve(symbol, timeframe, side)
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        end = (datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc))
        try:
            df = api.fetch(instrument, interval, offer,
                           start.replace(tzinfo=None), end.replace(tzinfo=None))
        except Exception as err:
            raise MarketDataError(f"{symbol} {timeframe} {year}-{month:02d}: {err}") from err
        df = self._normalise(df)
        if complete:
            path.write_bytes(pickle.dumps(df))
        return df

    @staticmethod
    def _normalise(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            # Must be float, not the default object dtype: an empty month
            # concatenated with real ones upcasts every column to object, and
            # the arithmetic downstream then fails on None instead of NaN.
            return pd.DataFrame({c: pd.Series(dtype=float) for c in COLUMNS},
                                index=pd.DatetimeIndex([], tz="UTC"))
        df = df.rename(columns=str.lower)
        missing = [c for c in COLUMNS if c not in df.columns]
        if missing:
            if missing == ["volume"]:
                df["volume"] = 0.0   # the index feed carries no volume
            else:
                raise MarketDataError(f"columns missing from the feed: {missing}")
        df = df[COLUMNS].astype(float)
        idx = pd.DatetimeIndex(df.index)
        df.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        return df[~df.index.duplicated(keep="last")].sort_index()

    def candles(self, symbol: str, timeframe: str, start: datetime, end: datetime,
                side: str = BID) -> pd.DataFrame:
        if start >= end:
            raise MarketDataError(f"empty range {start} .. {end}")
        start, end = _as_utc(start), _as_utc(end)
        frames, cursor = [], datetime(start.year, start.month, 1, tzinfo=timezone.utc)
        while cursor < end:
            frames.append(self._month(symbol, timeframe, side, cursor.year, cursor.month))
            cursor = datetime(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1,
                              tzinfo=timezone.utc)
        df = pd.concat(frames) if frames else pd.DataFrame(columns=COLUMNS)
        # Consecutive monthly fetches overlap: Dukascopy returns the last bar of
        # a month in both that month's range and the next one's. Left in, those
        # duplicates are counted twice by every indicator and swing downstream.
        df = df[~df.index.duplicated(keep="last")].sort_index()
        df = df[(df.index >= start) & (df.index < end)]
        df = df.astype(float)   # belt and braces after the concat
        if df.empty:
            raise MarketDataError(f"no {symbol} {timeframe} candles in {start} .. {end}")
        df = self._patch_holes(df, symbol, timeframe, side)
        _check_sane(df, symbol, timeframe)
        return df

    def _patch_holes(self, df: pd.DataFrame, symbol: str, timeframe: str,
                     side: str) -> pd.DataFrame:
        """Rebuild whole months the sparser feeds are simply missing.

        Dukascopy's 4h series has no data at all for WTI in July 2023 or Brent
        in July 2024, while the 1h series over the same months is complete.
        Left alone those holes are worse than missing data: the alignment in
        `scanner` carries the last bar before the hole forward, so a decision
        in the middle of July reads a trend from the end of June and nothing
        in the output says so. Filled from the lower timeframe they are exact.
        """
        source = DERIVE_FROM.get(timeframe)
        if source is None or len(df) < 2:
            return df
        span = df.index.to_series().diff()
        holes = [(when - span[when], when)
                 for when in span.index[span > MAX_MARKET_CLOSURE]]
        patches = []
        for previous, following in holes:
            try:
                lower = self.candles(symbol, source, previous, following, side)
            except MarketDataError as err:
                logging.warning(f"{symbol} {timeframe}: hole {previous} .. {following} "
                                f"cannot be filled from {source}: {err}")
                continue
            built = resample(lower, timeframe)
            built = built[(built.index > previous) & (built.index < following)]
            if built.empty:
                continue
            logging.warning(f"{symbol} {timeframe}: {len(built)} bars rebuilt from "
                            f"{source} to fill {previous} .. {following}")
            patches.append(built)
        if not patches:
            return df
        out = pd.concat([df] + patches)
        # keep="first": where both exist the native bar wins, though the
        # comparison above says they are the same bar either way.
        return out[~out.index.duplicated(keep="first")].sort_index()


def _as_utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def _check_sane(df: pd.DataFrame, symbol: str, timeframe: str):
    """Catch the malformed candles of spec item 34 before they reach a decision."""
    if df.index.duplicated().any():
        raise MarketDataError(f"{symbol} {timeframe}: duplicate candle timestamps")
    if not df.index.is_monotonic_increasing:
        raise MarketDataError(f"{symbol} {timeframe}: candles out of order")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise MarketDataError(f"{symbol} {timeframe}: non-positive prices in the feed")
    if (df["high"] < df["low"]).any():
        raise MarketDataError(f"{symbol} {timeframe}: high below low in the feed")
    bad = (df["high"] < df[["open", "close"]].max(axis=1)) | \
          (df["low"] > df[["open", "close"]].min(axis=1))
    if bad.any():
        raise MarketDataError(f"{symbol} {timeframe}: {int(bad.sum())} candles with "
                              "open/close outside the high/low range")


def resample(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Build higher timeframe candles from lower ones, when a feed lacks them."""
    rule = TIMEFRAMES[timeframe]
    out = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna(subset=["open", "high", "low", "close"])


def default_provider() -> DataProvider:
    return DukascopyProvider()


def staleness(df: pd.DataFrame, timeframe: str) -> timedelta:
    """How far behind the last candle is — spec item 34: never trade on stale data."""
    if df.empty:
        raise MarketDataError("no candles at all")
    last_close = df.index[-1] + TIMEFRAMES[timeframe]
    return datetime.now(timezone.utc) - last_close


def require_fresh(df: pd.DataFrame, timeframe: str, max_lag: timedelta):
    lag = staleness(df, timeframe)
    if lag > max_lag:
        raise MarketDataError(f"data is {lag} behind (limit {max_lag}) — no trade")
    logging.debug(f"{timeframe} data lag: {lag}")
