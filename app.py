import asyncio

from aiogram import executor

from data.config import ADMINS
from loader import dp, db
import middlewares, filters, handlers
from trading.monitor import run_monitor
from utils.notify_admins import on_startup_notify
from utils.set_bot_commands import set_default_commands


async def on_startup(dispatcher):
    # Default commands (/start and /help)
    await set_default_commands(dispatcher)

    # Notify admin that the bot has started
    await on_startup_notify(dispatcher)

    # Admins always receive signals
    for admin in ADMINS:
        db.subscribe(int(admin))

    # Watch the market in the background
    asyncio.create_task(run_monitor(dispatcher.bot, db))


if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup)
