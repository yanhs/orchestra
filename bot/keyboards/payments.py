"""
Inline-клавиатуры для страниц подтверждения и проведения оплаты.

get_payment_confirm_kb — кнопки «Оплатить» (внешняя ссылка) + «Отмена».
get_stars_payment_kb   — кнопка нативной оплаты Telegram Stars (pay=True).
"""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.callbacks import ServiceCB

# ---------------------------------------------------------------------------
# Подтверждение оплаты через внешний провайдер (ЮКасса / USDT)
# ---------------------------------------------------------------------------


def get_payment_confirm_kb(invoice_url: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для подтверждения оплаты через внешний URL.

    Args:
        invoice_url: прямая ссылка на страницу оплаты (ЮКасса, USDT-адрес и т.д.).

    Returns:
        InlineKeyboardMarkup:
            • [💳 Перейти к оплате] — url-кнопка
            • [❌ Отмена]           — callback-кнопка
    """
    builder = InlineKeyboardBuilder()

    # URL-кнопка открывает страницу оплаты во встроенном браузере
    builder.button(
        text="💳 Перейти к оплате",
        url=invoice_url,
    )

    builder.button(
        text="❌ Отмена",
        callback_data=ServiceCB(action="cancel"),
    )

    # Кнопки — каждая на своей строке
    builder.adjust(1)

    return builder.as_markup()


# ---------------------------------------------------------------------------
# Оплата через Telegram Stars (нативный платёж)
# ---------------------------------------------------------------------------


def get_stars_payment_kb() -> InlineKeyboardMarkup:
    """
    Клавиатура для нативной оплаты через Telegram Stars.

    Содержит специальную кнопку с ``pay=True``, которая запускает
    встроенный флоу оплаты Telegram (отправляется вместе с invoice).

    Returns:
        InlineKeyboardMarkup:
            • [⭐ Оплатить Stars] — pay-кнопка (должна быть первой!)
            • [❌ Отмена]         — callback-кнопка
    """
    builder = InlineKeyboardBuilder()

    # ВАЖНО: кнопка pay=True ДОЛЖНА идти первой в списке кнопок,
    # иначе Telegram вернёт ошибку BadRequest.
    builder.button(
        text="⭐ Оплатить Stars",
        pay=True,
    )

    builder.button(
        text="❌ Отмена",
        callback_data=ServiceCB(action="cancel"),
    )

    # Каждая кнопка на отдельной строке
    builder.adjust(1)

    return builder.as_markup()
