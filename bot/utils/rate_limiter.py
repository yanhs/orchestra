"""
Sliding Window Rate Limiter на базе Redis Sorted Set.

Использует атомарный Lua-скрипт (ZADD + ZREMRANGEBYSCORE + ZCARD)
для гарантии корректности при конкурентных запросах.

Members = uuid4 (не timestamp) — исключает коллизии при одновременных запросах.
"""

from __future__ import annotations

import time
import uuid
from typing import Final

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

KEY_PREFIX: Final[str] = "rl:flood"

# ---------------------------------------------------------------------------
# Lua-скрипт: атомарный check-and-increment.
#
# KEYS[1] — ключ sorted set
# ARGV[1] — текущий timestamp (float, секунды)
# ARGV[2] — начало допустимого окна (timestamp - window_seconds)
# ARGV[3] — max_requests
# ARGV[4] — uuid4-member
# ARGV[5] — TTL ключа в секундах (window + 10)
#
# Логика:
#   1. Удалить устаревшие записи (score < window_start)
#   2. Подсчитать текущее количество
#   3. Если < max_requests — добавить новую запись, установить EXPIRE, вернуть 1
#   4. Иначе — вернуть 0 (лимит превышен)
# ---------------------------------------------------------------------------
_CHECK_AND_INCREMENT_SCRIPT: Final[str] = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_start = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local member = ARGV[4]
local ttl_seconds = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

local current = redis.call('ZCARD', key)

if current < max_requests then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, ttl_seconds)
    return 1
end

return 0
"""

# ---------------------------------------------------------------------------
# Lua-скрипт: получить оставшееся количество запросов.
#
# KEYS[1] — ключ sorted set
# ARGV[1] — начало допустимого окна (timestamp - window_seconds)
# ARGV[2] — max_requests
#
# Возвращает: max_requests - текущий_count (но не меньше 0)
# ---------------------------------------------------------------------------
_GET_REMAINING_SCRIPT: Final[str] = """
local key = KEYS[1]
local window_start = tonumber(ARGV[1])
local max_requests = tonumber(ARGV[2])

redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

local current = redis.call('ZCARD', key)
local remaining = max_requests - current

if remaining < 0 then
    return 0
end

return remaining
"""


class RateLimiter:
    """
    Sliding-window rate limiter с Redis Sorted Set.

    Использование::

        redis = Redis.from_url("redis://localhost:6379/0")
        limiter = RateLimiter(redis=redis)

        allowed = await limiter.check_and_increment(
            user_id=123456,
            max_requests=10,
            window_seconds=60,
        )
        if not allowed:
            # пользователь превысил лимит
            ...
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._check_script = self._redis.register_script(_CHECK_AND_INCREMENT_SCRIPT)
        self._remaining_script = self._redis.register_script(_GET_REMAINING_SCRIPT)

    # ------------------------------------------------------------------
    # Построение ключа
    # ------------------------------------------------------------------

    @staticmethod
    def _build_key(user_id: int) -> str:
        return f"{KEY_PREFIX}:{user_id}"

    # ------------------------------------------------------------------
    # Публичное API
    # ------------------------------------------------------------------

    async def check_and_increment(
        self,
        user_id: int,
        max_requests: int,
        window_seconds: int,
    ) -> bool:
        """
        Проверяет лимит и, если запрос разрешён, атомарно инкрементирует счётчик.

        Returns:
            True  — запрос разрешён (счётчик увеличен).
            False — лимит исчерпан (счётчик НЕ увеличен).
        """
        key = self._build_key(user_id)
        now = time.time()
        window_start = now - window_seconds
        member = str(uuid.uuid4())
        ttl = window_seconds + 10

        try:
            result: int = await self._check_script(
                keys=[key],
                args=[now, window_start, max_requests, member, ttl],
            )
            allowed = result == 1

            if not allowed:
                logger.debug(
                    "rate_limit.exceeded",
                    user_id=user_id,
                    max_requests=max_requests,
                    window_seconds=window_seconds,
                )

            return allowed

        except RedisError as exc:
            logger.error(
                "rate_limit.redis_error",
                user_id=user_id,
                error=str(exc),
            )
            # При ошибке Redis — пропускаем, чтобы не блокировать пользователя
            return True

    async def get_remaining(
        self,
        user_id: int,
        max_requests: int,
        window_seconds: int,
    ) -> int:
        """
        Возвращает количество оставшихся запросов в текущем окне.

        При ошибке Redis возвращает max_requests (оптимистичный fallback).
        """
        key = self._build_key(user_id)
        window_start = time.time() - window_seconds

        try:
            remaining: int = await self._remaining_script(
                keys=[key],
                args=[window_start, max_requests],
            )
            return int(remaining)

        except RedisError as exc:
            logger.error(
                "rate_limit.remaining_redis_error",
                user_id=user_id,
                error=str(exc),
            )
            return max_requests

    async def reset(self, user_id: int) -> None:
        """
        Полностью сбрасывает счётчик запросов пользователя.
        """
        key = self._build_key(user_id)

        try:
            await self._redis.delete(key)
            logger.info("rate_limit.reset", user_id=user_id)

        except RedisError as exc:
            logger.error(
                "rate_limit.reset_redis_error",
                user_id=user_id,
                error=str(exc),
            )
