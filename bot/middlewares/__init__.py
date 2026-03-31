"""
Middlewares package for aiogram 3.x bot.

Порядок применения (outer → inner):
  Throttle → DB Session → UserCheck → Logging → Handler

Регистрация в dispatcher:
    dp.update.outer_middleware(ThrottleMiddleware(redis=redis_client))
    dp.update.middleware(DbSessionMiddleware(session_pool=async_session_maker))
    dp.update.middleware(UserContextMiddleware())
    dp.update.middleware(LoggingMiddleware())
"""

from .db_session import DbSessionMiddleware
from .throttle import ThrottleMiddleware
from .user_check import UserContextMiddleware

__all__ = [
    "DbSessionMiddleware",
    "ThrottleMiddleware",
    "UserContextMiddleware",
]
