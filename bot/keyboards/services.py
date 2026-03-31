"""
Inline-клавиатуры для всех AI-сервисов бота.

Каждая функция возвращает готовый InlineKeyboardMarkup.
Во всех клавиатурах присутствует кнопка ❌ Отмена (ServiceCB action='cancel').
"""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.callbacks import (
    GenerationCB,
    ResumeCB,
    ServiceCB,
    SummarizationCB,
    TranslationCB,
)

# ---------------------------------------------------------------------------
# Вспомогательная функция
# ---------------------------------------------------------------------------

def _cancel_button(builder: InlineKeyboardBuilder) -> None:
    """Добавляет кнопку ❌ Отмена в отдельный ряд клавиатуры."""
    builder.row(
        builder.button(
            text="❌ Отмена",
            callback_data=ServiceCB(action="cancel"),
        )
    )


# ---------------------------------------------------------------------------
# Генерация текста
# ---------------------------------------------------------------------------

def get_content_type_kb() -> InlineKeyboardMarkup:
    """
    Шаг 1 генерации: выбор типа контента.

    Варианты: Статья, Пост, Письмо, Описание товара.
    """
    builder = InlineKeyboardBuilder()

    items = [
        ("📰 Статья",        "article"),
        ("📱 Пост",          "post"),
        ("✉️ Письмо",        "letter"),
        ("🛍️ Описание",      "product"),
    ]

    for text, value in items:
        builder.button(
            text=text,
            callback_data=GenerationCB(step="ctype", value=value),
        )

    # 2 кнопки в ряд
    builder.adjust(2)
    _cancel_button(builder)

    return builder.as_markup()


def get_tone_kb() -> InlineKeyboardMarkup:
    """
    Шаг 2 генерации: выбор тональности текста.

    Варианты: Нейтральная, Официальная, Дружелюбная, Убедительная, Юмористическая.
    """
    builder = InlineKeyboardBuilder()

    tones = [
        ("😐 Нейтральная",      "neutral"),
        ("🏛️ Официальная",      "formal"),
        ("😊 Дружелюбная",      "friendly"),
        ("💼 Убедительная",     "persuasive"),
        ("😄 Юмористическая",   "humorous"),
    ]

    for text, value in tones:
        builder.button(
            text=text,
            callback_data=GenerationCB(step="tone", value=value),
        )

    # 2 кнопки в ряд, последняя сама по себе
    builder.adjust(2, 2, 1)
    _cancel_button(builder)

    return builder.as_markup()


# ---------------------------------------------------------------------------
# Перевод
# ---------------------------------------------------------------------------

def get_target_lang_kb() -> InlineKeyboardMarkup:
    """
    Выбор целевого языка перевода.

    Языки: RU / EN / DE / FR / ES / ZH + Auto-detect (определить автоматически).
    """
    builder = InlineKeyboardBuilder()

    languages = [
        ("🇷🇺 Русский",    "ru"),
        ("🇬🇧 English",    "en"),
        ("🇩🇪 Deutsch",    "de"),
        ("🇫🇷 Français",   "fr"),
        ("🇪🇸 Español",    "es"),
        ("🇨🇳 中文",        "zh"),
    ]

    for text, lang in languages:
        builder.button(
            text=text,
            callback_data=TranslationCB(lang=lang),
        )

    # Авто-определение языка — отдельная строка
    builder.button(
        text="🔁 Авто",
        callback_data=TranslationCB(lang="auto"),
    )

    # 2 кнопки в ряд для основных языков, авто — одна
    builder.adjust(2, 2, 2, 1)
    _cancel_button(builder)

    return builder.as_markup()


# ---------------------------------------------------------------------------
# Суммаризация
# ---------------------------------------------------------------------------

def get_output_format_kb() -> InlineKeyboardMarkup:
    """
    Выбор формата вывода суммаризации.

    Форматы: Краткий, Подробный, Bullet-points.
    """
    builder = InlineKeyboardBuilder()

    formats = [
        ("⚡ Краткий",        "short"),
        ("📖 Подробный",      "detail"),
        ("📌 Пункты",         "bullet"),
    ]

    for text, fmt in formats:
        builder.button(
            text=text,
            callback_data=SummarizationCB(fmt=fmt),
        )

    # 3 кнопки в один ряд
    builder.adjust(3)
    _cancel_button(builder)

    return builder.as_markup()


# ---------------------------------------------------------------------------
# Помощь с резюме
# ---------------------------------------------------------------------------

def get_resume_help_type_kb() -> InlineKeyboardMarkup:
    """
    Выбор типа помощи с резюме.

    Варианты: Написать с нуля, Улучшить существующее, Сопроводительное письмо.
    """
    builder = InlineKeyboardBuilder()

    help_types = [
        ("✏️ Написать резюме",       "write"),
        ("🔧 Улучшить резюме",       "improve"),
        ("📨 Cover Letter",          "cover"),
    ]

    for text, help_type in help_types:
        builder.button(
            text=text,
            callback_data=ResumeCB(help_type=help_type),
        )

    # Каждый вариант — на отдельной строке для удобства чтения
    builder.adjust(1)
    _cancel_button(builder)

    return builder.as_markup()
