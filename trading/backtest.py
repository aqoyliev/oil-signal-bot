"""Walks through history and simulates every setup the bot would have sent.
Signals come from 4h candles; zones, stops and targets are followed on 1h
candles with the same Setup.step() the live bot uses.

Run:  python -m trading.backtest
"""
import pandas as pd

from .data import INSTRUMENTS, TIMEFRAME, fetch_hourly, to_4h
from .setups import build_setup
from .strategy import DEFAULT_PARAMS, Params, compute_signals

SPREAD = 0.04  # USD per barrel, round-trip cost (spread + commission) per filled zone


def run(hourly: pd.DataFrame, p: Params = DEFAULT_PARAMS, spread: float = SPREAD) -> pd.DataFrame:
    """One row per filled zone. One setup per instrument at a time."""
    signals = compute_signals(to_4h(hourly), p)
    idx = hourly.index
    o, h, l, c = (hourly[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    rows, busy_until = [], None
    for ts, row in signals[signals.signal != 0].iterrows():
        end = ts + TIMEFRAME
        if busy_until is not None and end <= busy_until:
            continue
        setup = build_setup("", int(row.signal), row.Close, row.atr, row.bb_mid, end, p)
        j = idx.searchsorted(end)
        while setup.active and j < len(idx):
            setup.step(idx[j], o[j], h[j], l[j], c[j])
            j += 1
        busy_until = idx[j - 1]  # last candle the setup looked at (same rule as the live monitor)
        for k, z in enumerate(setup.zones):
            if z.entry is not None:
                rows.append({"time": end, "side": "BUY" if setup.side == 1 else "SELL", "zone": k + 1,
                             "entry": z.entry, "tp_hit": z.tp_hit, "reason": z.exit_reason,
                             "pnl": z.pnl - spread})
    return pd.DataFrame(rows)


def summary(trades: pd.DataFrame) -> dict:
    """win_rate: closed in profit. tp1_rate: reached TP1 (how most signal
    channels count a "win", even if the rest closes at break-even)."""
    if trades.empty:
        return {"setups": 0, "trades": 0, "tp1_rate": 0.0, "win_rate": 0.0,
                "profit_factor": 0.0, "total_pnl": 0.0, "max_dd": 0.0}
    wins = trades[trades.pnl > 0].pnl.sum()
    losses = -trades[trades.pnl <= 0].pnl.sum()
    equity = trades.pnl.cumsum()
    return {
        "setups": int(trades.time.nunique()),
        "trades": len(trades),
        "tp1_rate": round(float(100 * (trades.tp_hit >= 1).mean()), 1),
        "win_rate": round(float(100 * (trades.pnl > 0).mean()), 1),
        "profit_factor": round(float(wins / losses), 2) if losses else float("inf"),
        "total_pnl": round(float(trades.pnl.sum()), 2),
        "max_dd": round(float((equity.cummax() - equity).max()), 2),
    }


def main():
    for sym in INSTRUMENTS:
        trades = run(fetch_hourly(sym, "730d"))
        print(f"{sym}: {summary(trades)}  (pnl in USD per 1 barrel per zone)")
        if not trades.empty:
            print(trades.tail(6).to_string(index=False), "\n")


if __name__ == "__main__":
    main()
