"""
DB Session Middleware для aiogram 3.x.

Создаёт AsyncSession из пула для каждого апдейта,
кладёт в data['session'], коммитит после хендлера,
откатывает при исключении.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """
    Middleware, предоставляющий AsyncSession для каждого апдейта.

    Использование:
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        dp.update.middleware(DbSessionMiddleware(session_pool=session_pool))

    В хендлере:
        async def handler(message: Message, session: AsyncSession) -> None:
            ...
    """

    def __init__(self, session_pool: async_sessionmaker[AsyncSession]) -> None:
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_pool() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.exception(
                    "SQLAlchemy error during update handling, rolled back: %s", exc
                )
                raise
            except Exception:
                await session.rollback()
                raise
