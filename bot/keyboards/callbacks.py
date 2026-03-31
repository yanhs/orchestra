"""
CallbackData-фабрики для всех inline-клавиатур бота.

Правила именования:
  - prefix — максимально короткий (3-4 символа), чтобы итоговый pack() < 64 байт.
  - Все строковые поля ограничены короткими значениями (см. документацию ниже).
  - Целочисленные поля (amount) передаются напрямую как int.

Проверка длины (пример наихудшего случая):
  PayMethodCB(provider="yukassa", plan_id="pro_y", amount=99900).pack()
  → "pay:yukassa:pro_y:99900"  = 22 символа  ✓
"""

from aiogram.filters.callback_data import CallbackData


class ServiceCB(CallbackData, prefix="svc"):
    """
    Навигация по главному меню сервисов.

    action: 'gen' | 'trl' | 'sum' | 'rsm' | 'plan' | 'prf' | 'ref' | 'cancel'
    """

    action: str


class GenerationCB(CallbackData, prefix="gen"):
    """
    Шаги сценария генерации текста.

    step : 'ctype' | 'tone' | 'confirm' | 'cancel'
    value: конкретное значение шага, например 'article', 'formal', 'yes'
    """

    step: str
    value: str


class TranslationCB(CallbackData, prefix="trl"):
    """
    Выбор целевого языка перевода.

    lang: 'ru' | 'en' | 'de' | 'fr' | 'es' | 'zh' | 'auto' | 'cancel'
    """

    lang: str


class SummarizationCB(CallbackData, prefix="sum"):
    """
    Выбор формата вывода суммаризации.

    fmt: 'short' | 'detail' | 'bullet' | 'cancel'
    """

    fmt: str


class ResumeCB(CallbackData, prefix="rsm"):
    """
    Выбор типа помощи с резюме.

    help_type: 'write' | 'improve' | 'cover' | 'cancel'
    """

    help_type: str


class PlanCB(CallbackData, prefix="plan"):
    """
    Выбор тарифного плана и периода.

    plan_id: 'base' | 'pro' | 'ultra'
    period : 'mo'  (месяц) | 'yr' (год)
    """

    plan_id: str
    period: str


class PayMethodCB(CallbackData, prefix="pay"):
    """
    Выбор способа оплаты.

    provider: 'stars' | 'yukassa' | 'usdt'
    plan_id : 'base' | 'pro' | 'ultra'
    amount  : сумма в минимальных единицах (копейки / stars / cents)

    Пример pack(): "pay:stars:pro:500"  → 16 символов  ✓
    """

    provider: str
    plan_id: str
    amount: int


class ProfileCB(CallbackData, prefix="prf"):
    """
    Действия на странице профиля.

    action: 'info' | 'history' | 'settings' | 'logout' | 'cancel'
    """

    action: str


class ReferralCB(CallbackData, prefix="ref"):
    """
    Действия в реферальном разделе.

    action: 'link' | 'stats' | 'withdraw' | 'cancel'
    """

    action: str
