# CLAUDE.md

Telegram signal bot for WTI/Brent crude oil. See `README.md` for the strategy,
the signal format and the backtest numbers — this file only covers things that
are easy to get wrong.

## Run

```bash
python app.py                 # bot (polling) + signal monitor
python -m trading.backtest    # re-run the historical simulation
```

There are no tests and no linter config. Verify changes with the backtest and
by reading `trading/setups.py` carefully.

## Rules that are easy to break

**One poller at a time.** The bot is deployed on Railway (project
`oil-signal-bot`, service `bot`). Telegram returns `Conflict` on `getUpdates`
if a local `python app.py` runs while the deploy is live — stop one before
starting the other.

**Backtest and live must share `Setup.step()`.** `trading/setups.py` holds every
zone/SL/TP/break-even rule. `trading/backtest.py` feeds it 1h candles and
`trading/monitor.py` feeds it closed 15m candles; neither re-implements the
logic. Changing a rule in only one of them silently breaks parity — put it in
`setups.py`.

**Closed candles only.** `trading/data.py` drops the in-progress candle
(`_closed`). Using it would make signals repaint. Yahoo has no 4h interval, so
4h candles are 1h resampled (`to_4h`), and futures data is delayed ~10 minutes.

**Every user-facing string goes in `utils/i18n.py`**, in both `uz` and `en`, and
is rendered per subscriber language. Never hardcode text in a handler.

**Python 3.11.** aiogram 2.x needs aiohttp 3.8, which has no wheels for 3.12+.
`runtime.txt` pins this on Railway; use 3.11 locally too.

## Deployment

`railway up -s bot --ci` from PowerShell — Git Bash mangles Railway's
`--mount-path /data` argument into a Windows path.

The SQLite volume is mounted at `/data` with `DB_PATH=/data/bot.db`. It must
**not** be `/app/data`: the repo has a `data/` Python package and the mount
would shadow it, so the app would fail to import its config.

## Secrets

The repo is **public** (`aqoyliev/oil-signal-bot`). `.env` and `data/bot.db` are
gitignored and must stay that way; `.env.example` holds placeholders only. The
bot token and `ANTHROPIC_API_KEY` live in Railway variables.

## Windows notes

Write files with `encoding="utf-8"` and run scripts with `PYTHONIOENCODING=utf-8`
— the default cp1252 codec chokes on the emoji used in the signal messages.
