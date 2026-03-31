"""
UserContext Middleware для aiogram 3.x.

При каждом апдейте:
  1. Определяет Telegram-пользователя из события.
  2. Ищет его в БД (AsyncSession уже должен быть в data['session']).
  3. Если не найден — авто-регистрирует (создаёт новую запись).
  4. Кладёт ORM-объект в data['user'].

Ботов пропускает без обращения к БД.
Обрабатывает Message, CallbackQuery и произвольные TelegramObject.
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Длина реферального кода (base62)
_REFERRAL_CODE_LENGTH: int = 8
_REFERRAL_ALPHABET: str = string.ascii_letters + string.digits


def _generate_referral_code() -> str:
    """Генерирует криптографически стойкий base62-код длиной 8 символов."""
    return "".join(secrets.choice(_REFERRAL_ALPHABET) for _ in range(_REFERRAL_CODE_LENGTH))


def _extract_telegram_user(event: TelegramObject) -> User | None:
    """Извлекает объект User из любого поддерживаемого типа события."""
    if isinstance(event, Message):
        return event.from_user
    if isinstance(event, CallbackQuery):
        return event.from_user
    # Универсальный fallback для inline_query, chosen_inline_result и т.д.
    return getattr(event, "from_user", None)


class UserContextMiddleware(BaseMiddleware):
    """
    Middleware авто-регистрации и загрузки пользователя.

    Предполагает, что:
    - В data['session'] уже лежит AsyncSession (установлен DbSessionMiddleware).
    - ORM-модель импортируется из bot.models.user.
    - Модель User содержит поля:
        telegram_id  : int (PK или уникальный индекс)
        username     : str | None
        first_name   : str
        last_name    : str | None
        is_active    : bool (default True)
        created_at   : datetime
        referral_code: str (уникальный)
        referred_by  : int | None  — telegram_id пригласившего

    Использование:
        dp.update.middleware(UserContextMiddleware())

    В хендлере:
        async def handler(message: Message, user: User) -> None:
            ...
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: User | None = _extract_telegram_user(event)

        # Пропускаем события без пользователя или от ботов
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        session: AsyncSession = data["session"]

        db_user = await self._get_or_create_user(session, tg_user)
        data["user"] = db_user

        return await handler(event, data)

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    async def _get_or_create_user(
        self,
        session: AsyncSession,
        tg_user: User,
    ) -> Any:
        """
        Ищет пользователя в БД по telegram_id.
        Если не найден — создаёт. Всегда актуализирует username/имя.
        """
        # Импортируем модель здесь, чтобы избежать циклических зависимостей
        from bot.models.user import User as DbUser  # noqa: PLC0415

        stmt = select(DbUser).where(DbUser.telegram_id == tg_user.id)
        result = await session.execute(stmt)
        db_user: DbUser | None = result.scalar_one_or_none()

        if db_user is None:
            db_user = await self._create_user(session, tg_user, DbUser)
            logger.info(
                "Auto-registered new user: telegram_id=%s username=@%s",
                tg_user.id,
                tg_user.username,
            )
        else:
            # Актуализируем изменившиеся данные профиля
            changed = False
            if db_user.username != tg_user.username:
                db_user.username = tg_user.username
                changed = True
            if db_user.first_name != tg_user.first_name:
                db_user.first_name = tg_user.first_name
                changed = True
            if db_user.last_name != tg_user.last_name:
                db_user.last_name = tg_user.last_name
                changed = True
            if changed:
                logger.debug(
                    "Updated profile for telegram_id=%s", tg_user.id
                )

        return db_user

    @staticmethod
    async def _create_user(
        session: AsyncSession,
        tg_user: User,
        DbUser: Any,
    ) -> Any:
        """Создаёт и добавляет нового пользователя в сессию."""
        referral_code = await _unique_referral_code(session, DbUser)

        new_user = DbUser(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            is_active=True,
            created_at=datetime.now(tz=timezone.utc),
            referral_code=referral_code,
            referred_by=None,
        )
        session.add(new_user)
        # flush нужен, чтобы получить id до commit (если используется SERIAL PK)
        await session.flush([new_user])
        return new_user


async def _unique_referral_code(session: AsyncSession, DbUser: Any) -> str:
    """
    Генерирует уникальный реферальный код.
    В крайне маловероятном случае коллизии — повторяет попытку.
    """
    from bot.models.user import User as DbUser  # noqa: PLC0415, F811

    for _ in range(10):
        code = _generate_referral_code()
        existing = await session.execute(
            select(DbUser).where(DbUser.referral_code == code)
        )
        if existing.scalar_one_or_none() is None:
            return code
    # Последняя попытка без проверки (практически невозможная ситуация)
    return _generate_referral_code()
