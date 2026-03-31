"""
Alembic async environment configuration for ai-telegram-bot.
Supports PostgreSQL with asyncpg driver.
"""
import asyncio
import logging
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# ---------------------------------------------------------------------------
# Alembic Config object — gives access to alembic.ini values
# ---------------------------------------------------------------------------
config = context.config

# ---------------------------------------------------------------------------
# Logging — interpret the alembic.ini [loggers] section if present
# ---------------------------------------------------------------------------
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# ---------------------------------------------------------------------------
# Load DATABASE_URL
# ---------------------------------------------------------------------------
# Try python-dotenv first (optional dependency), fall back to os.environ
try:
    from dotenv import load_dotenv

    load_dotenv()
    logger.debug("Loaded environment from .env file via python-dotenv")
except ImportError:
    logger.debug("python-dotenv not installed — using os.environ only")

DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Set it in .env or export it before running alembic."
    )

# ---------------------------------------------------------------------------
# Normalise the URL to an asyncpg dialect
#   postgresql://...        → postgresql+asyncpg://...
#   postgresql+psycopg2://... → postgresql+asyncpg://...
#   postgres://...          → postgresql+asyncpg://...  (Heroku-style)
# ---------------------------------------------------------------------------
def _make_async_url(url: str) -> str:
    """Return a URL that uses the asyncpg driver."""
    # Replace common sync prefixes with the asyncpg one
    replacements = [
        ("postgresql+psycopg2://", "postgresql+asyncpg://"),
        ("postgresql+psycopg://", "postgresql+asyncpg://"),
        ("postgres://", "postgresql+asyncpg://"),
    ]
    for old, new in replacements:
        if url.startswith(old):
            return url.replace(old, new, 1)
    # Already asyncpg or plain postgresql:// → ensure asyncpg
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


ASYNC_DATABASE_URL = _make_async_url(DATABASE_URL)

# ---------------------------------------------------------------------------
# Import declarative Base and ALL models so Alembic can autogenerate diffs
# ---------------------------------------------------------------------------
try:
    from bot.db.engine import Base  # noqa: F401 — needed for metadata
    from bot.db import models  # noqa: F401 — registers all ORM classes
except ImportError as exc:
    logger.warning(
        "Could not import bot.db modules (%s). "
        "Autogenerate will use an empty MetaData.",
        exc,
    )
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):  # type: ignore[no-redef]
        pass

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Offline migrations (no DB connection required)
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and without an Engine.
    Calls to context.execute() emit the given string to the script output.
    """
    logger.info("Running migrations in OFFLINE mode")

    context.configure(
        url=ASYNC_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Include schemas if you use them
        include_schemas=False,
        # Render AS TIMEZONE for TIMESTAMPTZ columns
        render_as_batch=False,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online async migrations
# ---------------------------------------------------------------------------

def do_run_migrations(connection: Connection) -> None:
    """Execute migrations using an existing synchronous-compatible connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=False,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine, obtain a connection, run migrations."""
    logger.info("Running migrations in ONLINE (async) mode against: %s", ASYNC_DATABASE_URL)

    connectable = create_async_engine(
        ASYNC_DATABASE_URL,
        # Echo SQL for debug; switch to False in production
        echo=False,
        # Pool settings suitable for a one-off migration run
        pool_pre_ping=True,
    )

    async with connectable.connect() as connection:
        # run_sync allows us to call the synchronous Alembic context API
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — wraps the async runner."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entrypoint — Alembic calls this module as a script
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
