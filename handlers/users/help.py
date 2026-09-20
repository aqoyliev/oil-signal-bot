from aiogram import types
from aiogram.dispatcher.filters.builtin import CommandHelp

from loader import dp, db
from utils.i18n import t


@dp.message_handler(CommandHelp())
async def bot_help(message: types.Message):
    await message.answer(t(db.get_lang(message.chat.id), "help"))
