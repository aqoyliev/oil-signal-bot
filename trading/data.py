import pandas as pd
import yfinance as yf

# Yahoo Finance tickers: front-month futures (CME WTI, ICE Brent).
# Note: Yahoo futures quotes are delayed by ~10 minutes.
INSTRUMENTS = {
    "WTI": {"ticker": "CL=F", "name": "WTI Crude Oil (USOIL)"},
    "BRENT": {"ticker": "BZ=F", "name": "Brent Crude Oil (UKOIL)"},
}

TIMEFRAME = pd.Timedelta(hours=4)
INTERVALS = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1)}


def _download(symbol: str, interval: str, period: str) -> pd.DataFrame:
    df = yf.download(INSTRUMENTS[symbol]["ticker"], period=period, interval=interval,
                     progress=False, auto_adjust=False, multi_level_index=False)
    return df[["Open", "High", "Low", "Close"]].dropna()


def _closed(df: pd.DataFrame, length: pd.Timedelta) -> pd.DataFrame:
    """Drop the still-forming last candle."""
    if df.empty:
        return df
    return df[df.index + length <= pd.Timestamp.now(tz=df.index.tz)]


def fetch_hourly(symbol: str, period: str = "60d") -> pd.DataFrame:
    return _download(symbol, "1h", period)


def fetch_bars(symbol: str, interval: str = "15m", period: str = "5d") -> pd.DataFrame:
    """Closed intraday candles, used to follow open setups."""
    return _closed(_download(symbol, interval, period), INTERVALS[interval])


def to_4h(hourly: pd.DataFrame) -> pd.DataFrame:
    """Yahoo has no 4h interval, so build 4h candles from 1h ones."""
    return hourly.resample(TIMEFRAME).agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()


def fetch_candles(symbol: str, period: str = "60d", closed_only: bool = True) -> pd.DataFrame:
    """4h candles. With closed_only the still-forming last candle is dropped."""
    df = to_4h(fetch_hourly(symbol, period))
    return _closed(df, TIMEFRAME) if closed_only else df


def last_price(symbol: str) -> float:
    return float(fetch_hourly(symbol, "2d")["Close"].iloc[-1])
