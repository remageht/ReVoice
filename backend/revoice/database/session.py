"""
SQLite session management using SQLAlchemy async.
"""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from ..config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings.ensure_dirs()
    # Use str() to handle Cyrillic paths on Windows
    url = f"sqlite+aiosqlite:///{settings.db_path.as_posix()}"
    return create_async_engine(
        url,
        echo=False,
        connect_args={"check_same_thread": False},
    )


engine = _make_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency for getting a DB session."""
    async with AsyncSessionLocal() as session:
        yield session
