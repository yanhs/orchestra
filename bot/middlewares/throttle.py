"""
Throttle Middleware для aiogram 3.x.

Ограничение: не более 1 сообщения в секунду на пользователя.
Реализация: атомарный Lua-скрипт (INCR + PEXPIRE за одну транзакцию).
При превышении лимита — отправляем cooldown-сообщение, handler НЕ вызывается.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Final

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Период ограничения в миллисекундах (1 секунда)
RATE_LIMIT_MS: Final[int] = 1_000
# Максимально допустимое число запросов за период
MAX_REQUESTS: Final[int] = 1
# Ключ throttle в Redis: throttle:{user_id}
KEY_PREFIX: Final[str] = "throttle"

# ---------------------------------------------------------------------------
# Lua-скрипт: атомарный INCR + PEXPIRE.
# Возвращает текущий счётчик после инкремента.
# PEXPIRE устанавливается только при первом обращении (cnt == 1),
# чтобы не обновлять TTL при каждом запросе внутри окна.
# ---------------------------------------------------------------------------
_THROTTLE_SCRIPT: Final[str] = """
local key = KEYS[1]
local limit_ms = tonumber(ARGV[1])
local cnt = redis.call('INCR', key)
if cnt == 1 then
    redis.call('PEXPIRE', key, limit_ms)
end
return cnt
"""


class ThrottleMiddleware(BaseMiddleware):
    """
    Rate-limiting middleware на базе Redis с атомарным Lua-скриптом.

    Использование:
        redis_client = Redis.from_url("redis://localhost:6379/0")
        dp.update.outer_middleware(ThrottleMiddleware(redis=redis_client))

    Параметры:
        redis       — экземпляр redis.asyncio.Redis
        rate_limit  — длина окна в секундах (по умолчанию 1.0)
        max_requests — допустимое число запросов в окне (по умолчанию 1)
    """

    def __init__(
        self,
        redis: Redis,
        rate_limit: float = 1.0,
        max_requests: int = MAX_REQUESTS,
    ) -> None:
        self._redis = redis
        self._rate_limit_ms: int = int(rate_limit * 1000)
        self._max_requests = max_requests
        # Регистрируем скрипт один раз для переиспользования SHA
        self._script = self._redis.register_script(_THROTTLE_SCRIPT)

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _build_key(self, user_id: int) -> str:
        return f"{KEY_PREFIX}:{user_id}"

    async def _is_throttled(self, user_id: int) -> tuple[bool, int]:
        """
        Выполняет Lua-скрипт и возвращает (throttled, current_count).
        """
        key = self._build_key(user_id)
        count: int = await self._script(keys=[key], args=[self._rate_limit_ms])
        return count > self._max_requests, count

    @staticmethod
    def _extract_user_id(event: TelegramObject) -> int | None:
        """Извлекает user_id из любого поддерживаемого типа события."""
        if isinstance(event, Message) and event.from_user:
            return event.from_user.id
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user.id
        # Для остальных типов апдейтов пробуем универсальный путь
        from_user = getattr(event, "from_user", None)
        if from_user:
            return from_user.id
        return None

    @staticmethod
    async def _answer_throttled(event: TelegramObject, cooldown_sec: float) -> None:
        """Отправляет сообщение о превышении лимита."""
        text = (
            f"⏳ Слишком много запросов. "
            f"Пожалуйста, подождите {cooldown_sec:.1f} сек."
        )
        try:
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send throttle notification: %s", exc)

    # ------------------------------------------------------------------
    # Основной метод
    # ------------------------------------------------------------------

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = self._extract_user_id(event)

        if user_id is None:
            # Не можем идентифицировать пользователя — пропускаем без ограничений
            return await handler(event, data)

        try:
            throttled, count = await self._is_throttled(user_id)
        except Exception as exc:  # noqa: BLE001
            # При недоступности Redis не блокируем работу бота
            logger.error(
                "Redis error in ThrottleMiddleware (user_id=%s): %s", user_id, exc
            )
            return await handler(event, data)

        if throttled:
            logger.debug(
                "Throttled user_id=%s (count=%d, limit=%d)",
                user_id,
                count,
                self._max_requests,
            )
            cooldown_sec = self._rate_limit_ms / 1000
            await self._answer_throttled(event, cooldown_sec)
            # Возвращаем None — handler не вызывается
            return None

        return await handler(event, data)
