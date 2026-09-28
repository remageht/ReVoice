"""
Database migration — creates all tables on first run.
"""
from __future__ import annotations
import logging
from .session import engine, Base
from . import models  # noqa: F401 — registers all ORM models

logger = logging.getLogger(__name__)


async def run_migrations() -> None:
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database migrations applied.")
