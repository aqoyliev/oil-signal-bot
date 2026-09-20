"""Background loop: turns 4h signals into zone setups and follows them on
15-minute candles, sending a message for every entry, TP, SL and cancel."""
import asyncio
import logging

import pandas as pd

from utils.i18n import t
from .data import INSTRUMENTS, TIMEFRAME, fetch_bars, fetch_candles
from .setups import Setup, build_setup
from .strategy import DEFAULT_PARAMS as P, compute_signals

CHECK_EVERY = 5 * 60  # seconds
TASHKENT = "Asia/Tashkent"


def now(tz) -> pd.Timestamp:
    return pd.Timestamp.now(tz=tz)


def fmt_time(ts: pd.Timestamp) -> str:
    return ts.tz_convert(TASHKENT).strftime("%d.%m %H:%M")


def side_text(lang: str, side: int) -> str:
    return t(lang, "buy" if side == 1 else "sell")


def signal_message(lang: str, setup: Setup, rsi_value: float) -> str:
    signal_time = pd.Timestamp(setup.signal_time)
    valid_hours = (pd.Timestamp(setup.expires) - signal_time).total_seconds() / 3600
    parts = [t(lang, "signal_head", side=side_text(lang, setup.side),
               name=INSTRUMENTS[setup.symbol]["name"], price=setup.price, rsi=rsi_value)]
    for n, z in enumerate(setup.zones, 1):
        parts.append(t(lang, "zone_block", n=n, top=z.top, bottom=z.bottom, sl=z.sl,
                       tp1=z.tps[0], tp2=z.tps[1], tp3=z.tps[2], tp4=z.tps[3]))
    parts.append(t(lang, "signal_foot", valid=valid_hours, hold=setup.max_hold_hours,
                   time=fmt_time(signal_time)))
    return "\n\n".join(parts)


def event_line(lang: str, setup: Setup, event) -> str:
    _, i, kind, price = event
    z, n = setup.zones[i], i + 1
    if kind == "filled":
        return t(lang, "ev_filled", n=n, price=price)
    if kind == "cancelled":
        return t(lang, "ev_cancelled", n=n)
    if kind == "tp1":
        return t(lang, "ev_tp1", n=n, price=price, entry=z.entry)
    if kind in ("tp2", "tp3"):
        return t(lang, "ev_tp", n=n, k=kind[2], price=price)
    if kind == "timeout":
        return t(lang, "ev_timeout", n=n, hold=setup.max_hold_hours, price=price, pnl=z.pnl)
    return t(lang, f"ev_{kind}", n=n, price=price, pnl=z.pnl)  # tp4, sl, be


def update_message(lang: str, setup: Setup, events: list) -> str:
    head = t(lang, "update_head", side=side_text(lang, setup.side), name=INSTRUMENTS[setup.symbol]["name"])
    return "\n".join([head, ""] + [event_line(lang, setup, e) for e in events])


async def broadcast(bot, db, render):
    """`render(lang)` builds the message in each subscriber's language."""
    for chat_id, lang in db.subscribers():
        try:
            await bot.send_message(chat_id, render(lang))
        except Exception as err:
            logging.warning(f"Send to {chat_id} failed: {err}")


async def follow_setup(bot, db, row):
    """Feed the new closed 15m candles to an active setup and report what happened."""
    setup = Setup.from_json(row["state"])
    bars = await asyncio.to_thread(fetch_bars, row["symbol"])
    start = pd.Timestamp(setup.signal_time)
    last = pd.Timestamp(setup.last_time) if setup.last_time else None
    events = []
    for ts, bar in bars.iterrows():
        if not setup.active:
            break
        if ts < start or (last is not None and ts <= last):
            continue
        events += setup.step(ts, bar.Open, bar.High, bar.Low, bar.Close)
    db.save_setup(row["id"], setup.to_json(), setup.active)
    if events:
        await broadcast(bot, db, lambda lang: update_message(lang, setup, events))


async def check_new_signal(bot, db, symbol: str, last_row):
    df = compute_signals(await asyncio.to_thread(fetch_candles, symbol, "60d"))
    if df.empty:
        return
    ts, row = df.index[-1], df.iloc[-1]
    end = ts + TIMEFRAME
    # Only a fresh candle (closed within the last 4h) that was not handled yet
    if row.signal == 0 or now(ts.tz) - end >= TIMEFRAME:
        return
    if last_row is not None:
        prev = Setup.from_json(last_row["state"])
        if end <= pd.Timestamp(prev.last_time or prev.signal_time):
            return  # this candle closed while the previous setup was still running
    setup = build_setup(symbol, int(row.signal), row.Close, row.atr, row.bb_mid, end, P)
    db.add_setup(symbol, setup.signal_time, setup.to_json())
    await broadcast(bot, db, lambda lang: signal_message(lang, setup, row.rsi))


async def check_symbol(bot, db, symbol: str):
    last_row = db.last_setup(symbol)
    if last_row is not None and last_row["active"]:
        await follow_setup(bot, db, last_row)
    else:
        await check_new_signal(bot, db, symbol, last_row)


async def run_monitor(bot, db):
    logging.info("Signal monitor started")
    while True:
        for symbol in INSTRUMENTS:
            try:
                await check_symbol(bot, db, symbol)
            except Exception:
                logging.exception(f"Monitor error for {symbol}")
        await asyncio.sleep(CHECK_EVERY)
