from aiogram import types
from aiogram.dispatcher.filters.builtin import CommandStart

from keyboards.inline.language import language_keyboard
from loader import dp, db
from utils.i18n import LANGS, t


@dp.message_handler(CommandStart())
async def bot_start(message: types.Message):
    db.subscribe(message.chat.id)
    await message.answer(t("uz", "choose_lang"), reply_markup=language_keyboard("start"))


@dp.message_handler(commands=["language", "lang"])
async def change_language(message: types.Message):
    await message.answer(t("uz", "choose_lang"), reply_markup=language_keyboard("set"))


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("lang:"))
async def language_chosen(call: types.CallbackQuery):
    _, lang, action = call.data.split(":")
    await call.answer()
    if lang not in LANGS:
        return
    db.set_lang(call.message.chat.id, lang)
    await call.message.edit_text(t(lang, "lang_set"))
    if action == "start":
        await call.message.answer(t(lang, "welcome", name=call.from_user.full_name))


@dp.message_handler(commands="stop")
async def bot_stop(message: types.Message):
    lang = db.get_lang(message.chat.id)
    db.unsubscribe(message.chat.id)
    await message.answer(t(lang, "stopped"))
