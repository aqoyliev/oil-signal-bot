from aiogram import types


async def set_default_commands(dp):
    await dp.bot.set_my_commands(
        [
            types.BotCommand("start", "Obuna / Subscribe"),
            types.BotCommand("signal", "Hozirgi holat / Current state"),
            types.BotCommand("stats", "Natijalar / Results"),
            types.BotCommand("language", "Til / Language"),
            types.BotCommand("stop", "To'xtatish / Unsubscribe"),
            types.BotCommand("help", "Yordam / Help"),
        ]
    )
