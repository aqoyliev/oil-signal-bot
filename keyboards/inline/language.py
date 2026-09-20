from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.i18n import LANGS


def language_keyboard(action: str = "set") -> InlineKeyboardMarkup:
    """`action` is echoed back in the callback: "start" also sends the welcome text."""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(*[InlineKeyboardButton(title, callback_data=f"lang:{code}:{action}")
                   for code, title in LANGS.items()])
    return keyboard
