"""
Inline-клавиатуры для раздела подписки / тарифов.

get_plans_kb   — список тарифных планов (динамически из БД/конфига).
get_pay_method_kb — выбор способа оплаты для конкретного плана.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.callbacks import PayMethodCB, PlanCB, ServiceCB

# ---------------------------------------------------------------------------
# Константы провайдеров оплаты
# ---------------------------------------------------------------------------

_PROVIDERS: list[tuple[str, str]] = [
    ("⭐ Telegram Stars", "stars"),
    ("💳 ЮКасса",         "yukassa"),
    ("₿ USDT (TRC-20)",  "usdt"),
]

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _add_cancel(builder: InlineKeyboardBuilder) -> None:
    """Добавляет кнопку ❌ Отмена."""
    builder.row(
        builder.button(
            text="❌ Отмена",
            callback_data=ServiceCB(action="cancel"),
        )
    )


def _format_price(amount_kopecks: int, currency: str = "₽") -> str:
    """
    Форматирует цену из копеек в читаемый вид.

    >>> _format_price(49900)
    '499 ₽'
    """
    rubles = amount_kopecks // 100
    return f"{rubles:,} {currency}".replace(",", " ")


# ---------------------------------------------------------------------------
# Клавиатура тарифных планов
# ---------------------------------------------------------------------------


def get_plans_kb(plans: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    Строит inline-клавиатуру со списком доступных тарифных планов.

    Args:
        plans: список словарей с ключами:
            - plan_id  (str)  : 'base' | 'pro' | 'ultra'
            - name     (str)  : отображаемое название, напр. «Pro»
            - price_mo (int)  : цена в месяц (копейки)
            - price_yr (int)  : цена в год (копейки)
            - emoji    (str)  : иконка плана (опционально, default '📦')

    Returns:
        InlineKeyboardMarkup: каждый план — 2 кнопки (месяц / год) в одном ряду.

    Example plans input:
        [
            {"plan_id": "base",  "name": "Base",  "price_mo": 29900,  "price_yr": 299900,  "emoji": "🌱"},
            {"plan_id": "pro",   "name": "Pro",   "price_mo": 79900,  "price_yr": 799900,  "emoji": "🚀"},
            {"plan_id": "ultra", "name": "Ultra", "price_mo": 149900, "price_yr": 1299900, "emoji": "💎"},
        ]
    """
    builder = InlineKeyboardBuilder()

    for plan in plans:
        plan_id: str = plan["plan_id"]
        name: str    = plan["name"]
        emoji: str   = plan.get("emoji", "📦")
        price_mo: int = plan["price_mo"]
        price_yr: int = plan["price_yr"]

        # Кнопка «месяц»
        builder.button(
            text=f"{emoji} {name} — {_format_price(price_mo)}/мес",
            callback_data=PlanCB(plan_id=plan_id, period="mo"),
        )

        # Кнопка «год» (со скидкой)
        discount_pct = round(100 - (price_yr / (price_mo * 12)) * 100)
        builder.button(
            text=f"📅 {name} год −{discount_pct}% — {_format_price(price_yr)}/год",
            callback_data=PlanCB(plan_id=plan_id, period="yr"),
        )

    # Каждый план — отдельная строка из 2 кнопок (месяц + год)
    builder.adjust(*([2] * len(plans)))

    _add_cancel(builder)
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Клавиатура выбора способа оплаты
# ---------------------------------------------------------------------------


def get_pay_method_kb(plan_id: str, amount: int) -> InlineKeyboardMarkup:
    """
    Строит inline-клавиатуру выбора способа оплаты.

    Args:
        plan_id: идентификатор выбранного плана ('base' | 'pro' | 'ultra').
        amount : сумма к оплате в минимальных единицах (копейки для RUB,
                 штуки для Stars, центы для USDT).

    Returns:
        InlineKeyboardMarkup с кнопками провайдеров оплаты + кнопкой отмены.
    """
    builder = InlineKeyboardBuilder()

    for label, provider in _PROVIDERS:
        builder.button(
            text=label,
            callback_data=PayMethodCB(
                provider=provider,
                plan_id=plan_id,
                amount=amount,
            ),
        )

    # Каждый провайдер на отдельной строке
    builder.adjust(1)

    _add_cancel(builder)
    return builder.as_markup()
