"""
FSM State-группы для всех AI-сервисов бота.

Каждый сервис изолирован в собственном StatesGroup —
это позволяет одновременно хранить независимые FSM-контексты
и упрощает поиск состояний при отладке.
"""

from aiogram.fsm.state import State, StatesGroup


class TextGenerationFSM(StatesGroup):
    """Генерация текстового контента (статья / пост / письмо и т.д.)."""

    # Шаг 1: выбор типа контента (статья, пост, письмо, описание)
    choosing_content_type = State()

    # Шаг 2: выбор тональности (нейтральная, официальная, дружелюбная и т.д.)
    choosing_tone = State()

    # Шаг 3: ввод пользовательского промта / темы
    waiting_for_prompt = State()

    # Шаг 4: генерация выполняется (заблокировано для ввода)
    processing = State()


class TranslationFSM(StatesGroup):
    """Перевод текста на выбранный язык."""

    # Шаг 1: выбор целевого языка перевода
    choosing_target_lang = State()

    # Шаг 2: ожидание текста от пользователя
    waiting_for_text = State()

    # Шаг 3: выполнение перевода
    processing = State()


class SummarizationFSM(StatesGroup):
    """Суммаризация / краткое изложение документа или текста."""

    # Шаг 1: выбор формата вывода (краткий / подробный / bullet-points)
    choosing_output_format = State()

    # Шаг 2: ожидание исходного контента (текст или пересланное сообщение)
    waiting_for_content = State()

    # Шаг 3: выполнение суммаризации
    processing = State()


class ResumeHelpFSM(StatesGroup):
    """Помощь с резюме: написание, улучшение или сопроводительное письмо."""

    # Шаг 1: выбор типа помощи (написать / улучшить / cover letter)
    choosing_help_type = State()

    # Шаг 2: ввод целевой должности / роли
    entering_target_role = State()

    # Шаг 3: ожидание резюме (текст, PDF или документ)
    waiting_for_resume = State()

    # Шаг 4: обработка и генерация результата
    processing = State()


class SubscriptionFSM(StatesGroup):
    """Покупка / продление подписки."""

    # Шаг 1: выбор тарифного плана
    choosing_plan = State()

    # Шаг 2: выбор способа оплаты (Stars / ЮКасса / USDT)
    choosing_pay_method = State()

    # Шаг 3: ожидание подтверждения платежа
    awaiting_payment = State()
