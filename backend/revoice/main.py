"""
ReVoice FastAPI application.
Точка входа для uvicorn и sidecar-бинаря.
"""
from __future__ import annotations
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database.migrations import run_migrations

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# Always register stub engines at import time
from .backends import stub_engine  # noqa: F401
try:
    from .backends import qwen_engine  # noqa: F401
except ImportError as e:
    logger.warning("Qwen engine not available: %s", e)

try:
    from .backends import fish_engine  # noqa: F401
except ImportError as e:
    logger.warning("Fish engine not available: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    logger.info("ReVoice server starting up...")
    settings.ensure_dirs()
    await run_migrations()
    logger.info("ReVoice server ready on http://%s:%d", settings.host, settings.port)
    yield
    logger.info("ReVoice server shutting down.")


app = FastAPI(
    title="ReVoice API",
    description="Локальная студия клонирования голоса",
    version="0.1.5",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# CORS — только localhost для интеграций
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:7851",
        "http://127.0.0.1:7851",
        "tauri://localhost",
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
from .routes.health import router as health_router
from .routes.models import router as models_router
from .routes.profiles import router as profiles_router
from .routes.synthesize import router as synthesize_router
from .routes.effects import router as effects_router
from .routes.book import router as book_router

app.include_router(health_router)
app.include_router(models_router)
app.include_router(profiles_router)
app.include_router(synthesize_router)
app.include_router(effects_router)
app.include_router(book_router)


@app.get("/")
async def root() -> dict:
    return {"app": "ReVoice", "version": "0.1.5", "docs": "/docs"}
