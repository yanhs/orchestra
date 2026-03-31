"""
Главное Reply-меню бота.

Используется ReplyKeyboardMarkup, чтобы кнопки всегда были
видны пользователю — не нужно каждый раз вызывать команду.
"""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def get_main_menu(user_name: str = "") -> ReplyKeyboardMarkup:
    """
    Возвращает главное меню бота.

    Args:
        user_name: имя пользователя (не используется в кнопках,
                   но может применяться в приветственном сообщении).

    Returns:
        ReplyKeyboardMarkup с 7 кнопками в 2 колонки + 1 широкая.
    """
    builder = ReplyKeyboardBuilder()

    # Ряд 1: AI-сервисы
    builder.row(
        KeyboardButton(text="✍️ Генерация"),
        KeyboardButton(text="🌐 Перевод"),
    )

    # Ряд 2: документальные сервисы
    builder.row(
        KeyboardButton(text="📋 Суммаризация"),
        KeyboardButton(text="📄 Резюме"),
    )

    # Ряд 3: монетизация и профиль
    builder.row(
        KeyboardButton(text="💎 Тарифы"),
        KeyboardButton(text="👤 Профиль"),
    )

    # Ряд 4: реферальная программа (одна широкая кнопка)
    builder.row(
        KeyboardButton(text="🔗 Реферальная"),
    )

    return builder.as_markup(
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder=f"Привет, {user_name}! Выбери сервис 👇" if user_name else "Выбери сервис 👇",
    )
