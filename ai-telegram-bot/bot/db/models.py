"""ORM models for ai-telegram-bot (SQLAlchemy 2.0, asyncpg)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.engine import Base

# ── helpers ───────────────────────────────────────────────────────────────────
_now = func.now  # shortcut — evaluated at DB level


# ── User ──────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str] = mapped_column(String(10), default="ru", server_default="ru")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    subscription_type: Mapped[str] = mapped_column(
        String(20), default="free", server_default="free"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=_now(),
        onupdate=_now(),
    )
    referral_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    referred_by_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ── relationships ─────────────────────────────────────────────────────────
    subscription: Mapped[Subscription | None] = relationship(
        "Subscription", back_populates="user", uselist=False
    )
    payments: Mapped[list[Payment]] = relationship("Payment", back_populates="user")
    usage_logs: Mapped[list[UsageLog]] = relationship("UsageLog", back_populates="user")

    referred_by: Mapped[User | None] = relationship(
        "User", remote_side="User.id", foreign_keys=[referred_by_id]
    )
    referrals_given: Mapped[list[Referral]] = relationship(
        "Referral",
        foreign_keys="[Referral.referrer_id]",
        back_populates="referrer",
    )
    referral_received: Mapped[Referral | None] = relationship(
        "Referral",
        foreign_keys="[Referral.referred_id]",
        back_populates="referred",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} telegram_id={self.telegram_id} username={self.username!r}>"


# ── Subscription ──────────────────────────────────────────────────────────────
class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    plan: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="'free' | 'basic' | 'pro'"
    )
    requests_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    price_rub: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now()
    )
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now()
    )

    # ── relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="subscription")

    def __repr__(self) -> str:
        return f"<Subscription id={self.id} user_id={self.user_id} plan={self.plan!r}>"


# ── Payment ───────────────────────────────────────────────────────────────────
class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RUB", server_default="RUB")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'pending' | 'completed' | 'failed' | 'refunded'",
    )
    payment_provider: Mapped[str] = mapped_column(
        String(50), default="yookassa", server_default="yookassa"
    )
    external_payment_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    subscription_plan: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=_now(),
        onupdate=_now(),
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True
    )

    # ── relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="payments")

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} user_id={self.user_id} "
            f"amount={self.amount} status={self.status!r}>"
        )


# ── UsageLog ──────────────────────────────────────────────────────────────────
class UsageLog(Base):
    __tablename__ = "usage_logs"

    __table_args__ = (
        Index("ix_usage_logs_user_id_request_date", "user_id", "request_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    request_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    ai_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    request_type: Mapped[str] = mapped_column(
        String(50), default="chat", server_default="chat"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now()
    )

    # ── relationships ─────────────────────────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="usage_logs")

    def __repr__(self) -> str:
        return (
            f"<UsageLog id={self.id} user_id={self.user_id} "
            f"date={self.request_date} tokens={self.tokens_used}>"
        )


# ── Referral ──────────────────────────────────────────────────────────────────
class Referral(Base):
    __tablename__ = "referrals"

    __table_args__ = (
        UniqueConstraint("referrer_id", "referred_id", name="uq_referral_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    referred_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    bonus_granted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    bonus_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now()
    )

    # ── relationships ─────────────────────────────────────────────────────────
    referrer: Mapped[User] = relationship(
        "User",
        foreign_keys=[referrer_id],
        back_populates="referrals_given",
    )
    referred: Mapped[User] = relationship(
        "User",
        foreign_keys=[referred_id],
        back_populates="referral_received",
    )

    def __repr__(self) -> str:
        return (
            f"<Referral id={self.id} referrer={self.referrer_id} "
            f"referred={self.referred_id} bonus={self.bonus_granted}>"
        )
