"""Initial database schema.

Creates all core tables:
    users, subscriptions, payments, usage_logs, referrals

Revision ID: 001_initial
Revises:     —
Created:     2026-03-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers — used by Alembic
# ---------------------------------------------------------------------------
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
TIMESTAMPTZ = sa.TIMESTAMP(timezone=True)


# ===========================================================================
# upgrade — create tables in dependency order
# ===========================================================================
def upgrade() -> None:

    # -----------------------------------------------------------------------
    # 1. users
    #    Self-referencing FK (referred_by_id → users.id) is added after the
    #    table exists via ADD CONSTRAINT to avoid circular-reference issues.
    # -----------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "telegram_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=False),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column(
            "language_code",
            sa.String(10),
            nullable=False,
            server_default="ru",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_banned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "subscription_type",
            sa.String(20),
            nullable=False,
            server_default="free",
        ),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=True),
        sa.Column("referral_code", sa.String(20), nullable=True),
        # Self-referencing FK — declared here; constraint added below
        sa.Column("referred_by_id", sa.BigInteger(), nullable=True),
        # Constraints
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
        sa.UniqueConstraint("referral_code", name="uq_users_referral_code"),
    )

    # Self-referencing FK (users.referred_by_id → users.id)
    op.create_foreign_key(
        "fk_users_referred_by_id",
        "users",
        "users",
        ["referred_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -----------------------------------------------------------------------
    # 2. subscriptions  (depends on: users)
    # -----------------------------------------------------------------------
    op.create_table(
        "subscriptions",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("plan", sa.String(20), nullable=False),
        sa.Column("requests_per_day", sa.Integer(), nullable=True),
        sa.Column("ai_model", sa.String(50), nullable=True),
        sa.Column("price_rub", sa.Numeric(10, 2), nullable=True),
        sa.Column("started_at", TIMESTAMPTZ, nullable=True),
        sa.Column("expires_at", TIMESTAMPTZ, nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "auto_renew",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Constraints
        sa.UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_subscriptions_user_id",
            ondelete="CASCADE",
        ),
    )

    # -----------------------------------------------------------------------
    # 3. payments  (depends on: users)
    # -----------------------------------------------------------------------
    op.create_table(
        "payments",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="RUB",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "payment_provider",
            sa.String(50),
            nullable=True,
            server_default="yookassa",
        ),
        sa.Column("external_payment_id", sa.String(255), nullable=True),
        sa.Column("subscription_plan", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        # Constraints
        sa.UniqueConstraint(
            "external_payment_id",
            name="uq_payments_external_payment_id",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_payments_user_id",
            ondelete="CASCADE",
        ),
    )

    # -----------------------------------------------------------------------
    # 4. usage_logs  (depends on: users)
    # -----------------------------------------------------------------------
    op.create_table(
        "usage_logs",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("request_date", sa.Date(), nullable=False),
        sa.Column("ai_model", sa.String(50), nullable=True),
        sa.Column(
            "tokens_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "request_type",
            sa.String(50),
            nullable=False,
            server_default="chat",
        ),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Constraints
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_usage_logs_user_id",
            ondelete="CASCADE",
        ),
    )

    # Composite index for efficient per-user / per-date queries
    op.create_index(
        "ix_usage_logs_user_date",
        "usage_logs",
        ["user_id", "request_date"],
        unique=False,
    )

    # -----------------------------------------------------------------------
    # 5. referrals  (depends on: users × 2)
    # -----------------------------------------------------------------------
    op.create_table(
        "referrals",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("referrer_id", sa.BigInteger(), nullable=False),
        sa.Column("referred_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "bonus_granted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("bonus_type", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # referred_id is globally unique — one user can only be referred once
        sa.UniqueConstraint("referred_id", name="uq_referrals_referred_id"),
        # The same (referrer, referred) pair must be unique
        sa.UniqueConstraint(
            "referrer_id",
            "referred_id",
            name="uq_referrals_referrer_referred",
        ),
        sa.ForeignKeyConstraint(
            ["referrer_id"],
            ["users.id"],
            name="fk_referrals_referrer_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["referred_id"],
            ["users.id"],
            name="fk_referrals_referred_id",
            ondelete="CASCADE",
        ),
    )


# ===========================================================================
# downgrade — drop tables in reverse dependency order
# ===========================================================================
def downgrade() -> None:
    # 5. referrals
    op.drop_table("referrals")

    # 4. usage_logs — drop index explicitly, then the table
    op.drop_index("ix_usage_logs_user_date", table_name="usage_logs")
    op.drop_table("usage_logs")

    # 3. payments
    op.drop_table("payments")

    # 2. subscriptions
    op.drop_table("subscriptions")

    # 1. users — drop self-referencing FK first, then the table
    op.drop_constraint("fk_users_referred_by_id", "users", type_="foreignkey")
    op.drop_table("users")
