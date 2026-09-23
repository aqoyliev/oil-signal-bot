"""Bot texts in Uzbek and English. Usage: t(lang, key, **format_kwargs)."""

LANGS = {"uz": "🇺🇿 O'zbekcha", "en": "🇬🇧 English"}
DEFAULT_LANG = "uz"

TEXTS = {
    "uz": {
        "choose_lang": "Tilni tanlang / Choose language:",
        "lang_set": "✅ Til: O'zbekcha",
        "welcome": (
            "Salom, {name}!\n\n"
            "Siz WTI va Brent neft signallariga obuna bo'ldingiz. "
            "Sotib olish/sotish vaqti kelganda xabar yuboraman.\n\n"
            "📷 Grafik skrinshotini yuborsangiz — tahlil qilib beraman.\n"
            "/help — buyruqlar ro'yxati"),
        "stopped": "Obuna bekor qilindi. Qayta yoqish uchun /start",
        "help": (
            "<b>Buyruqlar:</b>\n"
            "/start — signallarga obuna bo'lish\n"
            "/stop — obunani to'xtatish\n"
            "/signal — hozirgi holat (narx, RSI, faol signal)\n"
            "/stats — strategiyaning tarixiy natijalari\n"
            "/language — tilni o'zgartirish\n\n"
            "📷 Grafik skrinshotini yuboring — tahlil qilib beraman. "
            "Rasm ostiga savol ham yozishingiz mumkin.\n\n"
            "<b>Signal qanday ishlaydi:</b>\n"
            "• 2 ta zona: narx zonaga kelganda kiriladi, har bir zonaning o'z SL'i bor.\n"
            "• Har TP'da pozitsiyaning 1/4 qismi yopiladi.\n"
            "• TP1 dan keyin SL kirish narxiga ko'chiriladi (B/U).\n"
            "• Bot har bir kirish, TP, SL haqida alohida xabar beradi.\n\n"
            "Strategiya: 4 soatlik sham, Bollinger + RSI (mean reversion).\n"
            "⚠️ Signal — maslahat emas. Stop-loss'siz savdo qilmang."),
        "loading": "⏳ Ma'lumot olinyapti...",
        "price_line": "Narx: <b>{price:.2f}</b> | RSI(4H): {rsi:.1f}",
        "bands": "Bollinger: {low:.2f} / {mid:.2f} / {up:.2f}",
        "active_setup": "📌 Faol signal: {side}",
        "st_pending": "Zone {n}: ⏳ kutilmoqda ({top:.2f})",
        "st_open": "Zone {n}: 🟢 ochiq @ {entry:.2f}, TP {tp_hit}/4, SL {stop:.2f}",
        "st_closed": "Zone {n}: ✔️ yopildi ({pnl:+.2f} $)",
        "st_cancelled": "Zone {n}: ❌ bekor qilindi",
        "watch_low": "👀 Pastki chiziq ostida — RSI {lvl:.0f} dan tushsa BUY signali bo'ladi",
        "watch_high": "👀 Yuqori chiziq ustida — RSI {lvl:.0f} dan oshsa SELL signali bo'ladi",
        "no_signal": "Signal yo'q, kutyapmiz.",
        "last_candle": "<i>Oxirgi yopilgan sham: {time}</i>",
        "stats_loading": "⏳ 2 yillik tarix bo'yicha hisoblanyapti...",
        "stats_header": "<b>Backtest (oxirgi ~2 yil, spread hisobga olingan):</b>",
        "stats_row": (
            "\n<b>{name}</b>\n"
            "Signallar: {setups} | Savdolar (zona): {trades}\n"
            "Win rate: <b>{win_rate}%</b> | TP1 ga yetgan: {tp1}%\n"
            "Profit factor: {pf} | Jami: {total:+.2f} $/barrel\n"
            "Maks. drawdown: {dd:.2f} $/barrel"),
        "stats_live": "\n<b>Bot jonli signallari:</b> {n} ta savdo, win rate {wr:.0f}%, jami {total:+.2f} $/barrel",
        "stats_note": (
            "\n<i>Win rate — foyda bilan yopilgan savdolar. \"TP1 ga yetgan\" — ko'p signal "
            "kanallari \"win\" deb hisoblaydigan ko'rsatkich.</i>"),
        "stats_disclaimer": "<i>O'tmishdagi natija kelajakni kafolatlamaydi.</i>",
        "buy": "🟢 BUY",
        "sell": "🔴 SELL",
        "signal_head": "<b>{side} — {name}</b>\nNarx: <b>{price:.2f}</b> | RSI: {rsi:.1f} | 4H",
        "zone_block": (
            "📍 <b>Zone {n}:</b> {top:.2f}-{bottom:.2f}\n\n"
            "🛑 SL: {sl:.2f}\n"
            "🎯 TP1: {tp1:.2f} B/U qilinsin\n"
            "🎯 TP2: {tp2:.2f}\n"
            "🎯 TP3: {tp3:.2f}\n"
            "🎯 TP4: {tp4:.2f}"),
        "signal_foot": (
            "ℹ️ Har TP'da pozitsiyaning 1/4 qismini yoping. "
            "Zonalar {valid:.0f} soat amal qiladi, savdo maks. {hold:.0f} soat.\n"
            "🕒 {time} (Toshkent vaqti)"),
        "update_head": "<b>{side} — {name}</b>",
        "ev_filled": "📍 Zone {n} ishga tushdi: {price:.2f}",
        "ev_tp1": "🎯 Zone {n} TP1 ✅ {price:.2f} — 1/4 qismini yoping, SL ni {entry:.2f} ga ko'chiring (B/U)",
        "ev_tp": "🎯 Zone {n} TP{k} ✅ {price:.2f} — yana 1/4 qismini yoping",
        "ev_tp4": "🏁 Zone {n} TP4 ✅ {price:.2f} — savdo to'liq yopildi. Natija: <b>{pnl:+.2f} $</b>/barrel",
        "ev_sl": "🛑 Zone {n} stop-loss {price:.2f}. Natija: <b>{pnl:+.2f} $</b>/barrel",
        "ev_be": "⚖️ Zone {n}: narx kirishga qaytdi, qolgan qism B/U da ({price:.2f}) yopildi. "
                 "Natija: <b>{pnl:+.2f} $</b>/barrel",
        "ev_timeout": "⏳ Zone {n}: {hold:.0f} soat o'tdi — qolgan qismni yoping ({price:.2f}). "
                      "Natija: <b>{pnl:+.2f} $</b>/barrel",
        "ev_cancelled": "❌ Zone {n} bekor qilindi — narx zonaga kelmadi",
        "alert_head": "👀 <b>{name}</b> — {side} signaliga yaqin",
        "alert_buy": (
            "Narx: <b>{price:.2f}</b> | RSI: {rsi:.1f}\n"
            "Pastki chiziq: {band:.2f} — {dist:.1f}% qoldi\n\n"
            "4 soatlik sham shu chiziqdan pastda yopilsa va RSI {lvl:.0f} dan tushsa, "
            "signal yuboraman.\n"
            "⚠️ Hozir kirmang — tayyor turing."),
        "alert_sell": (
            "Narx: <b>{price:.2f}</b> | RSI: {rsi:.1f}\n"
            "Yuqori chiziq: {band:.2f} — {dist:.1f}% qoldi\n\n"
            "4 soatlik sham shu chiziqdan baland yopilsa va RSI {lvl:.0f} dan oshsa, "
            "signal yuboraman.\n"
            "⚠️ Hozir kirmang — tayyor turing."),
        "digest_head": "☀️ <b>Kunlik holat</b> — {date}",
        "digest_row": (
            "<b>{name}</b>\n"
            "Narx: <b>{price:.2f}</b> | RSI: {rsi:.1f}\n"
            "Bollinger: {low:.2f} / {mid:.2f} / {up:.2f}\n"
            "{verdict}"),
        "digest_foot": "<i>Signal chiqsa darhol xabar beraman. /signal — hozirgi holat.</i>",
        "vd_active": "📌 Faol signal: {side} — savdo davom etyapti, /signal ni bosing",
        "vd_near_buy": "👀 BUY signaliga yaqin — {level:.2f} ga {dist:.1f}% qoldi, "
                       "RSI {lvl:.0f} dan tushishi kerak. Tayyor turing.",
        "vd_near_sell": "👀 SELL signaliga yaqin — {level:.2f} ga {dist:.1f}% qoldi, "
                        "RSI {lvl:.0f} dan oshishi kerak. Tayyor turing.",
        "vd_neutral": (
            "⚪️ Signal yo'q — hozir kirmang, kutamiz.\n"
            "BUY uchun: narx {low:.2f} dan past ({dlow:+.1f}%), RSI {rl:.0f} dan past\n"
            "SELL uchun: narx {up:.2f} dan baland ({dup:+.1f}%), RSI {rh:.0f} dan baland"),
        "analyzing": "🔍 Grafik tahlil qilinyapti, biroz kuting...",
        "no_api_key": "⚠️ Tahlil funksiyasi hali sozlanmagan (ANTHROPIC_API_KEY yo'q).",
        "analysis_error": "❌ Tahlil qilib bo'lmadi. Birozdan keyin qayta urinib ko'ring.",
        "analysis_refused": "⚠️ Bu rasmni tahlil qila olmadim. Grafik skrinshotini yuboring.",
        "not_image": "Grafikni rasm (PNG/JPG) sifatida yuboring.",
        "too_fast": "⏳ Biroz sekinroq — {secs:.0f} soniyadan keyin qayta yuboring.",
    },
    "en": {
        "choose_lang": "Tilni tanlang / Choose language:",
        "lang_set": "✅ Language: English",
        "welcome": (
            "Hello, {name}!\n\n"
            "You are subscribed to WTI and Brent crude oil signals. "
            "I'll message you when it's time to buy or sell.\n\n"
            "📷 Send me a chart screenshot and I'll analyse it.\n"
            "/help — list of commands"),
        "stopped": "Unsubscribed. Send /start to subscribe again.",
        "help": (
            "<b>Commands:</b>\n"
            "/start — subscribe to signals\n"
            "/stop — unsubscribe\n"
            "/signal — current state (price, RSI, active signal)\n"
            "/stats — historical strategy results\n"
            "/language — change language\n\n"
            "📷 Send a chart screenshot and I'll analyse it. "
            "You can add a question as the caption.\n\n"
            "<b>How a signal works:</b>\n"
            "• 2 zones: enter when price reaches a zone; each zone has its own SL.\n"
            "• Close 1/4 of the position at each TP.\n"
            "• After TP1 move the SL to the entry price (break-even).\n"
            "• The bot sends a message for every entry, TP and SL.\n\n"
            "Strategy: 4h candles, Bollinger + RSI (mean reversion).\n"
            "⚠️ Signals are not financial advice. Never trade without a stop-loss."),
        "loading": "⏳ Fetching data...",
        "price_line": "Price: <b>{price:.2f}</b> | RSI(4H): {rsi:.1f}",
        "bands": "Bollinger: {low:.2f} / {mid:.2f} / {up:.2f}",
        "active_setup": "📌 Active signal: {side}",
        "st_pending": "Zone {n}: ⏳ waiting ({top:.2f})",
        "st_open": "Zone {n}: 🟢 open @ {entry:.2f}, TP {tp_hit}/4, SL {stop:.2f}",
        "st_closed": "Zone {n}: ✔️ closed ({pnl:+.2f} $)",
        "st_cancelled": "Zone {n}: ❌ cancelled",
        "watch_low": "👀 Below the lower band — BUY signal if RSI drops under {lvl:.0f}",
        "watch_high": "👀 Above the upper band — SELL signal if RSI rises over {lvl:.0f}",
        "no_signal": "No signal, waiting.",
        "last_candle": "<i>Last closed candle: {time}</i>",
        "stats_loading": "⏳ Calculating over 2 years of history...",
        "stats_header": "<b>Backtest (last ~2 years, spread included):</b>",
        "stats_row": (
            "\n<b>{name}</b>\n"
            "Signals: {setups} | Trades (zones): {trades}\n"
            "Win rate: <b>{win_rate}%</b> | Reached TP1: {tp1}%\n"
            "Profit factor: {pf} | Total: {total:+.2f} $/barrel\n"
            "Max drawdown: {dd:.2f} $/barrel"),
        "stats_live": "\n<b>Live bot signals:</b> {n} trades, win rate {wr:.0f}%, total {total:+.2f} $/barrel",
        "stats_note": (
            "\n<i>Win rate = trades closed in profit. \"Reached TP1\" is what many signal "
            "channels call a \"win\".</i>"),
        "stats_disclaimer": "<i>Past performance does not guarantee future results.</i>",
        "buy": "🟢 BUY",
        "sell": "🔴 SELL",
        "signal_head": "<b>{side} — {name}</b>\nPrice: <b>{price:.2f}</b> | RSI: {rsi:.1f} | 4H",
        "zone_block": (
            "📍 <b>Zone {n}:</b> {top:.2f}-{bottom:.2f}\n\n"
            "🛑 SL: {sl:.2f}\n"
            "🎯 TP1: {tp1:.2f} move SL to B/E\n"
            "🎯 TP2: {tp2:.2f}\n"
            "🎯 TP3: {tp3:.2f}\n"
            "🎯 TP4: {tp4:.2f}"),
        "signal_foot": (
            "ℹ️ Close 1/4 of the position at each TP. "
            "Zones are valid for {valid:.0f} hours, max trade duration {hold:.0f} hours.\n"
            "🕒 {time} (Tashkent time)"),
        "update_head": "<b>{side} — {name}</b>",
        "ev_filled": "📍 Zone {n} triggered: {price:.2f}",
        "ev_tp1": "🎯 Zone {n} TP1 ✅ {price:.2f} — close 1/4, move SL to {entry:.2f} (break-even)",
        "ev_tp": "🎯 Zone {n} TP{k} ✅ {price:.2f} — close another 1/4",
        "ev_tp4": "🏁 Zone {n} TP4 ✅ {price:.2f} — trade fully closed. Result: <b>{pnl:+.2f} $</b>/barrel",
        "ev_sl": "🛑 Zone {n} stop-loss {price:.2f}. Result: <b>{pnl:+.2f} $</b>/barrel",
        "ev_be": "⚖️ Zone {n}: price returned to entry, the rest closed at break-even ({price:.2f}). "
                 "Result: <b>{pnl:+.2f} $</b>/barrel",
        "ev_timeout": "⏳ Zone {n}: {hold:.0f} hours passed — close the rest ({price:.2f}). "
                      "Result: <b>{pnl:+.2f} $</b>/barrel",
        "ev_cancelled": "❌ Zone {n} cancelled — price did not reach the zone",
        "alert_head": "👀 <b>{name}</b> — close to a {side} signal",
        "alert_buy": (
            "Price: <b>{price:.2f}</b> | RSI: {rsi:.1f}\n"
            "Lower band: {band:.2f} — {dist:.1f}% away\n\n"
            "If a 4h candle closes below that band and RSI drops under {lvl:.0f}, "
            "I'll send the signal.\n"
            "⚠️ Don't enter yet — just get ready."),
        "alert_sell": (
            "Price: <b>{price:.2f}</b> | RSI: {rsi:.1f}\n"
            "Upper band: {band:.2f} — {dist:.1f}% away\n\n"
            "If a 4h candle closes above that band and RSI rises over {lvl:.0f}, "
            "I'll send the signal.\n"
            "⚠️ Don't enter yet — just get ready."),
        "digest_head": "☀️ <b>Daily status</b> — {date}",
        "digest_row": (
            "<b>{name}</b>\n"
            "Price: <b>{price:.2f}</b> | RSI: {rsi:.1f}\n"
            "Bollinger: {low:.2f} / {mid:.2f} / {up:.2f}\n"
            "{verdict}"),
        "digest_foot": "<i>I'll message you the moment a signal appears. /signal — current state.</i>",
        "vd_active": "📌 Active signal: {side} — the trade is still running, see /signal",
        "vd_near_buy": "👀 Close to a BUY signal — {dist:.1f}% from {level:.2f}, "
                       "RSI needs to drop under {lvl:.0f}. Get ready.",
        "vd_near_sell": "👀 Close to a SELL signal — {dist:.1f}% from {level:.2f}, "
                        "RSI needs to rise over {lvl:.0f}. Get ready.",
        "vd_neutral": (
            "⚪️ No signal — stay out for now.\n"
            "For BUY: price below {low:.2f} ({dlow:+.1f}%), RSI under {rl:.0f}\n"
            "For SELL: price above {up:.2f} ({dup:+.1f}%), RSI over {rh:.0f}"),
        "analyzing": "🔍 Analysing the chart, please wait...",
        "no_api_key": "⚠️ Chart analysis is not configured yet (ANTHROPIC_API_KEY missing).",
        "analysis_error": "❌ Analysis failed. Please try again in a moment.",
        "analysis_refused": "⚠️ I couldn't analyse this image. Please send a chart screenshot.",
        "not_image": "Please send the chart as an image (PNG/JPG).",
        "too_fast": "⏳ Slow down — try again in {secs:.0f} seconds.",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    text = TEXTS.get(lang, TEXTS[DEFAULT_LANG])[key]
    return text.format(**kwargs) if kwargs else text
