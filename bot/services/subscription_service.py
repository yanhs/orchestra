"""Subscription management service.

Handles plan checks, daily request limits (via atomic Redis Lua),
and subscription lifecycle (upgrade / expiry downgrade).

SQL schema (run once):
    CREATE TABLE IF NOT EXISTS subscriptions (
        user_id    BIGINT PRIMARY KEY,
        plan       VARCHAR(16) NOT NULL DEFAULT 'FREE',
        expires_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import asyncpg
import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_PLANS: dict[str, dict[str, Any]] = {
    "FREE":  {"daily_requests": 10},
    "BASIC": {"daily_requests": 100},
    "PRO":   {"daily_requests": -1},  # unlimited
}

_TTL_SECONDS: int = 25 * 3600  # 25 hours — covers timezone drift

# Lua: atomic check-and-increment in a single round-trip.
# Returns {0, current} when limit hit, {1, new_val} otherwise.
_LUA_CHECK_AND_INCR = """
local key   = KEYS[1]
local limit = tonumber(ARGV[1])
local ttl   = tonumber(ARGV[2])

local current = redis.call('GET', key)
if current and tonumber(current) >= limit then
    return {0, tonumber(current)}
end

local new_val = redis.call('INCR', key)
if new_val == 1 then
    redis.call('EXPIRE', key, ttl)
end
return {1, new_val}
"""


class SubscriptionService:
    """Manages user subscriptions and per-day request budgets."""

    __slots__ = ("_redis", "_pool", "_lua_sha")

    def __init__(self, redis: Redis, pool: asyncpg.Pool) -> None:
        self._redis = redis
        self._pool = pool
        self._lua_sha: str | None = None

    # ── helpers ───────────────────────────────────────────────────────────

    async def _ensure_lua_loaded(self) -> str:
        """Load the Lua script once and cache its SHA."""
        if self._lua_sha is None:
            self._lua_sha = await self._redis.script_load(_LUA_CHECK_AND_INCR)
        return self._lua_sha

    @staticmethod
    def _usage_key(user_id: int) -> str:
        today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
        return f"usage:count:{user_id}:{today}"

    # ── public API ────────────────────────────────────────────────────────

    async def can_make_request(self, user_id: int) -> tuple[bool, str]:
        """Atomically check the daily limit and increment the counter.

        Returns:
            (True,  "ok")           — request allowed
            (False, "<reason>")     — request denied with human-readable reason
        """
        try:
            sub = await self.get_subscription(user_id)
            plan = sub["plan"]
            limits = self.get_daily_limits(plan)
            daily_limit: int = limits["daily_requests"]

            # Unlimited plan — always allow, still increment for stats
            if daily_limit == -1:
                key = self._usage_key(user_id)
                pipe = self._redis.pipeline(transaction=False)
                pipe.incr(key)
                pipe.expire(key, _TTL_SECONDS)
                await pipe.execute()
                return True, "ok"

            sha = await self._ensure_lua_loaded()
            key = self._usage_key(user_id)
            result = await self._redis.evalsha(
                sha, 1, key, str(daily_limit), str(_TTL_SECONDS),
            )

            allowed = int(result[0])
            current = int(result[1])

            if allowed:
                return True, "ok"

            return (
                False,
                f"Дневной лимит исчерпан ({current}/{daily_limit}). "
                f"Обновите план для увеличения лимита.",
            )
        except Exception:
            logger.exception("can_make_request failed", user_id=user_id)
            # Fail-open: allow the request so users aren't blocked by infra issues
            return True, "ok"

    async def get_subscription(self, user_id: int) -> dict[str, Any]:
        """Fetch the user's subscription row from PostgreSQL.

        If the row does not exist a default FREE plan is returned (and created).
        """
        row = await self._pool.fetchrow(
            "SELECT user_id, plan, expires_at, created_at "
            "FROM subscriptions WHERE user_id = $1",
            user_id,
        )
        if row is not None:
            return dict(row)

        # Auto-create a FREE subscription for new users
        try:
            await self._pool.execute(
                "INSERT INTO subscriptions (user_id, plan) VALUES ($1, 'FREE') "
                "ON CONFLICT (user_id) DO NOTHING",
                user_id,
            )
        except asyncpg.UniqueViolationError:
            pass  # race condition — someone else inserted
        except Exception:
            logger.exception("Failed to auto-create subscription", user_id=user_id)

        return {
            "user_id": user_id,
            "plan": "FREE",
            "expires_at": None,
            "created_at": _dt.datetime.now(_dt.timezone.utc),
        }

    @staticmethod
    def get_daily_limits(plan: str) -> dict[str, Any]:
        """Return limit dict for *plan*.  Falls back to FREE on unknown plan."""
        return _PLANS.get(plan.upper(), _PLANS["FREE"])

    async def get_remaining_requests(self, user_id: int) -> int:
        """How many requests the user can still make today.

        Returns ``-1`` for unlimited plans.
        """
        sub = await self.get_subscription(user_id)
        limits = self.get_daily_limits(sub["plan"])
        daily_limit: int = limits["daily_requests"]

        if daily_limit == -1:
            return -1

        key = self._usage_key(user_id)
        current_raw = await self._redis.get(key)
        current = int(current_raw) if current_raw else 0
        return max(daily_limit - current, 0)

    async def upgrade_plan(
        self,
        user_id: int,
        plan: str,
        expires_at: _dt.datetime | None = None,
    ) -> None:
        """Set the user's subscription plan in PostgreSQL."""
        plan = plan.upper()
        if plan not in _PLANS:
            raise ValueError(f"Unknown plan: {plan}")

        await self._pool.execute(
            "INSERT INTO subscriptions (user_id, plan, expires_at) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (user_id) DO UPDATE "
            "SET plan = EXCLUDED.plan, expires_at = EXCLUDED.expires_at",
            user_id,
            plan,
            expires_at,
        )
        logger.info(
            "subscription_upgraded",
            user_id=user_id,
            plan=plan,
            expires_at=expires_at,
        )

    async def check_subscription_expiry(self, user_id: int) -> bool:
        """Check if subscription is expired; if so, downgrade to FREE.

        Returns ``True`` when the subscription is **still active** (or FREE).
        Returns ``False`` when the subscription was **just downgraded**.
        """
        sub = await self.get_subscription(user_id)

        if sub["plan"] == "FREE":
            return True

        expires_at: _dt.datetime | None = sub.get("expires_at")
        if expires_at is None:
            return True  # no expiry — lifetime plan

        now = _dt.datetime.now(_dt.timezone.utc)
        # Handle naive datetimes from the database
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=_dt.timezone.utc)

        if expires_at > now:
            return True  # still valid

        # Expired → downgrade
        await self._pool.execute(
            "UPDATE subscriptions SET plan = 'FREE', expires_at = NULL "
            "WHERE user_id = $1",
            user_id,
        )
        logger.warning(
            "subscription_expired_downgrade",
            user_id=user_id,
            old_plan=sub["plan"],
            expired_at=expires_at.isoformat(),
        )
        return False
