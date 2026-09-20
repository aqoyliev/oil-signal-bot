# Oil Signal Bot (WTI & Brent)

Telegram bot that watches **WTI (CL=F / USOIL)** and **Brent (BZ=F / UKOIL)** and
sends a message when it is time to **buy**, **sell**, and when to **close** the
position (take-profit, stop-loss or time-out). It only sends alerts — it never
places trades.

It also **analyses chart screenshots**: send the bot a TradingView / broker
screenshot (optionally with a question as the caption) and Claude reads the
chart and replies with bias, key levels and a trade idea.

Works in **Uzbek and English** — the user picks a language on `/start`.

Built on the aiogram 2.x template.

## Strategy

Signals come from Bollinger-band mean reversion on **4-hour candles**:

| | Rule |
|---|---|
| BUY | 4h candle closes below the lower band (20, 2σ) **and** RSI(14) < 30 |
| SELL | 4h candle closes above the upper band **and** RSI(14) > 70 |

Only closed candles are used, so signals do not repaint. Expect roughly one
signal per instrument per week.

### Signal format (zones + 4 take-profits)

Each signal is sent as two entry zones, each with its own stop-loss and four
take-profits:

```
🟢 BUY — WTI Crude Oil (USOIL)
📍 Zone 1: 81.12-80.28        📍 Zone 2: 79.03-78.19
🛑 SL: 72.74                  🛑 SL: 70.65
🎯 TP1: 83.45 B/U qilinsin    🎯 TP1..TP4: same as zone 1
🎯 TP2: 85.77
🎯 TP3: 88.10
🎯 TP4: 90.42
```

| | Rule |
|---|---|
| Zone 1 | starts at the signal price (width 0.3 × ATR) |
| Zone 2 | 0.75 × ATR deeper — averaging in if price overshoots |
| Stop-loss | 3 × ATR beyond each zone's edge |
| TP1–TP4 | 25 / 50 / 75 / 100 % of the way to the middle band; close 1/4 at each |
| Break-even | after TP1 the stop moves to the entry price |
| Expiry | unfilled zones are cancelled after 12 h, or if price reaches TP1 first |
| Time-out | whatever is still open is closed after 48 h |

The bot then follows the setup on 15-minute candles and sends a message for
every zone fill, TP, stop, break-even exit, time-out and cancellation.
`trading/setups.py` holds these rules; the backtest and the live bot both run
the same `Setup.step()` code.

### Backtest (Sep 2024 – Sep 2026, per zone, 1 barrel, $0.04 cost per trade)

| | Signals | Trades (zones) | Win rate | Reached TP1 | Profit factor | Total | Max drawdown |
|---|---|---|---|---|---|---|---|
| WTI | 78 | 109 | 69% | 62% | 1.53 | +$35.2 | $21.7 |
| Brent | 64 | 90 | 77% | 67% | 1.49 | +$26.1 | $24.8 |

"Win rate" = trades closed in profit. "Reached TP1" is what many signal
channels report as their win rate, even when the rest closes at break-even.

Split into the first 70% / last 30% of trades:

| | Profit factor (first 70%) | Profit factor (last 30%) |
|---|---|---|
| WTI | 0.91 | 2.29 |
| Brent | 1.20 | 2.36 |

Notes:
- Most of the profit comes from the volatile 2026 period; on WTI the calmer
  2024–2025 period was roughly break-even. Win rate was steadier (64–79%).
- The zone and TP settings were chosen from a grid search on the same data,
  so treat these numbers as optimistic.
- Trend strategies tested with a 70–80% win rate **lost money** out-of-sample,
  which is why they were not used.
- Yahoo Finance futures data is delayed ~10 minutes; broker CFD prices differ
  slightly from futures prices.

Re-run the backtest any time:

```bash
python -m trading.backtest
```

## Bot commands

| Command | Description |
|---|---|
| `/start` | Subscribe to signals |
| `/stop` | Unsubscribe |
| `/signal` | Current price, RSI, bands and the active signal's zones |
| `/stats` | Backtest results + live signal results |
| `/language` | Switch between Uzbek and English |
| `/help` | Help |
| 📷 photo | Send a chart screenshot to get an analysis |

Users listed in `ADMINS` are subscribed automatically.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env      # set BOT_TOKEN and ADMINS
python app.py
```

Chart analysis needs an Anthropic API key (`ANTHROPIC_API_KEY` in `.env`,
from [console.anthropic.com](https://console.anthropic.com)). Without it the
bot still sends signals; screenshots get a "not configured" reply.

The bot keeps subscribers and active signals in `data/bot.db` (SQLite), so it
survives restarts. It must run 24/5 (e.g. on a VPS) to catch every signal.

## Deployment (Railway)

The bot runs as a **worker** service (no HTTP port). Files that matter:
`Procfile`, `railway.json`, `runtime.txt` (pins Python 3.11 — aiogram 2.x needs
aiohttp 3.8, which has no wheels for 3.12+) and `.railwayignore`.

```bash
railway init --name oil-signal-bot          # create the project
railway add --service bot --variables "BOT_TOKEN=..." --variables "ADMINS=..."
railway volume add --mount-path /data       # persistent SQLite storage
railway variables --set "DB_PATH=/data/bot.db" --set "TZ=Asia/Tashkent"
railway up -s bot --ci                      # build and deploy
railway logs -s bot                          # runtime logs
```

`DB_PATH` must point inside the volume: the repository already has a `data/`
Python package, so mounting the volume at `/app/data` would shadow it and the
app would not start.

**Only one instance may poll Telegram at a time** — stop the local `python app.py`
before deploying, otherwise Telegram returns a `Conflict` error on `getUpdates`.

## Project structure

```
├── app.py                  # Entry point: polling + signal monitor
├── Procfile, railway.json  # Railway worker deployment
├── trading/
│   ├── data.py             # Yahoo Finance download, 1h -> 4h candles
│   ├── indicators.py       # EMA, RSI, ATR, ADX, Bollinger
│   ├── strategy.py         # Signal rules and parameters
│   ├── setups.py           # Zones, SL, TP1-TP4, break-even (shared by backtest and bot)
│   ├── backtest.py         # Historical simulation
│   ├── monitor.py          # Background loop, signal and trade-update alerts
│   └── analyst.py          # Chart screenshot analysis (Claude vision)
├── handlers/users/         # /start, /stop, /signal, /stats, /language, photos
├── utils/i18n.py           # Uzbek / English texts
└── utils/db_api/storage.py # SQLite: subscribers (with language) and signals
```

## Disclaimer

Signals are informational, not financial advice. Past results do not guarantee
future results. Always use a stop-loss and risk only what you can afford to lose.

## License

[MIT](LICENSE)
