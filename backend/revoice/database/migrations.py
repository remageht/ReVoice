"""
Database migration — creates all tables and applies schema updates.
"""
from __future__ import annotations
import logging
from sqlalchemy import text
from .session import engine, Base
from . import models  # noqa: F401 — registers all ORM models

logger = logging.getLogger(__name__)


async def run_migrations() -> None:
    """Create all tables and apply incremental schema updates."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Ensure incremental columns on voice_samples exist
        for col, col_type in [
            ("peak", "REAL"),
            ("verdict", "VARCHAR(200)"),
            ("rms_profile_json", "TEXT"),
        ]:
            try:
                await conn.execute(text(f"ALTER TABLE voice_samples ADD COLUMN {col} {col_type}"))
            except Exception:
                pass  # Column already exists

    logger.info("Database migrations applied.")
