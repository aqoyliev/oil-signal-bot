import asyncio

from aiogram import types

from loader import dp, db
from trading.backtest import run, summary
from trading.data import INSTRUMENTS, fetch_candles, fetch_hourly, last_price
from trading.monitor import fmt_time, side_text
from trading.setups import Setup
from trading.strategy import DEFAULT_PARAMS as P, compute_signals
from utils.i18n import t


def zone_status(lang: str, n: int, z) -> str:
    if z.status == "pending":
        return t(lang, "st_pending", n=n, top=z.top)
    if z.status == "open":
        return t(lang, "st_open", n=n, entry=z.entry, tp_hit=z.tp_hit, stop=z.stop)
    if z.status == "closed":
        return t(lang, "st_closed", n=n, pnl=z.pnl)
    return t(lang, "st_cancelled", n=n)


@dp.message_handler(commands="signal")
async def current_state(message: types.Message):
    lang = db.get_lang(message.chat.id)
    await message.answer(t(lang, "loading"))
    parts = []
    for symbol, info in INSTRUMENTS.items():
        df = compute_signals(await asyncio.to_thread(fetch_candles, symbol, "60d"))
        price = await asyncio.to_thread(last_price, symbol)
        row = df.iloc[-1]
        lines = [f"<b>{info['name']}</b>",
                 t(lang, "price_line", price=price, rsi=row.rsi),
                 t(lang, "bands", low=row.bb_low, mid=row.bb_mid, up=row.bb_up)]
        last = db.last_setup(symbol)
        if last is not None and last["active"]:
            setup = Setup.from_json(last["state"])
            lines.append(t(lang, "active_setup", side=side_text(lang, setup.side)))
            lines += [zone_status(lang, n, z) for n, z in enumerate(setup.zones, 1)]
        elif price < row.bb_low:
            lines.append(t(lang, "watch_low", lvl=P.rsi_low))
        elif price > row.bb_up:
            lines.append(t(lang, "watch_high", lvl=100 - P.rsi_low))
        else:
            lines.append(t(lang, "no_signal"))
        lines.append(t(lang, "last_candle", time=fmt_time(df.index[-1])))
        parts.append("\n".join(lines))
    await message.answer("\n\n".join(parts))


@dp.message_handler(commands="stats")
async def stats(message: types.Message):
    lang = db.get_lang(message.chat.id)
    await message.answer(t(lang, "stats_loading"))
    lines = [t(lang, "stats_header")]
    for symbol, info in INSTRUMENTS.items():
        s = summary(await asyncio.to_thread(lambda: run(fetch_hourly(symbol, "730d"))))
        lines.append(t(lang, "stats_row", name=info["name"], setups=s["setups"], trades=s["trades"],
                       win_rate=s["win_rate"], tp1=s["tp1_rate"], pf=s["profit_factor"],
                       total=s["total_pnl"], dd=s["max_dd"]))
    zones = [z for state in db.finished_setups() for z in Setup.from_json(state).zones if z.entry is not None]
    if zones:
        wins = sum(1 for z in zones if z.pnl > 0)
        lines.append(t(lang, "stats_live", n=len(zones), wr=100 * wins / len(zones),
                       total=sum(z.pnl for z in zones)))
    lines.append(t(lang, "stats_note"))
    lines.append(t(lang, "stats_disclaimer"))
    await message.answer("\n".join(lines))
