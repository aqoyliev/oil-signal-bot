import html
import io
import logging

from aiogram import types

from loader import dp, db
from trading import analyst
from utils.i18n import t

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
TELEGRAM_LIMIT = 4096


async def _analyze(message: types.Message, file, media_type: str):
    lang = db.get_lang(message.chat.id)
    if not analyst.enabled():
        await message.reply(t(lang, "no_api_key"))
        return
    wait = await message.reply(t(lang, "analyzing"))
    try:
        buf = await file.download(destination_file=io.BytesIO())
        text = await analyst.analyze_chart(buf.getvalue(), media_type, lang, message.caption)
    except Exception:
        logging.exception("Chart analysis failed")
        await wait.edit_text(t(lang, "analysis_error"))
        return
    if not text:
        await wait.edit_text(t(lang, "analysis_refused"))
        return
    # The model answers in plain text; escape so stray < > & don't break HTML mode
    await wait.edit_text(html.escape(text)[:TELEGRAM_LIMIT])


@dp.message_handler(content_types=types.ContentType.PHOTO)
async def analyze_photo(message: types.Message):
    await _analyze(message, message.photo[-1], "image/jpeg")  # Telegram re-encodes photos as JPEG


@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def analyze_document(message: types.Message):
    mime = message.document.mime_type or ""
    if mime not in IMAGE_TYPES:
        await message.reply(t(db.get_lang(message.chat.id), "not_image"))
        return
    await _analyze(message, message.document, mime)
