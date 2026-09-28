"""
ReVoice configuration — uses APPDATA/Revoice on Windows.
Кириллические пути поддерживаются через pathlib.
"""
from __future__ import annotations
import os
import sys
import logging
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

logger = logging.getLogger(__name__)


def _default_data_dir() -> Path:
    """Return %APPDATA%/Revoice on Windows, ~/.revoice elsewhere."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "Revoice"


def _default_models_dir() -> Path:
    return _default_data_dir() / "models"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REVOICE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = "127.0.0.1"
    port: int = 7851
    workers: int = 1
    log_level: str = "info"

    # Data dirs
    data_dir: Path = Field(default_factory=_default_data_dir)
    models_dir: Path = Field(default_factory=_default_models_dir)

    # DB
    db_name: str = "revoice.db"

    # GPU
    duty_cycle_limit: float = Field(default=0.8, ge=0.5, le=1.0)
    vram_budget_mb: int = Field(default=3500, ge=1024)

    # Generation defaults
    max_chunk_chars: int = Field(default=200, ge=50, le=1000)
    crossfade_ms: int = Field(default=50, ge=0, le=500)

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_name

    @property
    def voices_dir(self) -> Path:
        return self.data_dir / "voices"

    @property
    def generations_dir(self) -> Path:
        return self.data_dir / "generations"

    def ensure_dirs(self) -> None:
        for d in [self.data_dir, self.models_dir, self.voices_dir, self.generations_dir]:
            d.mkdir(parents=True, exist_ok=True)
        logger.info("Data dir: %s", self.data_dir)


settings = Settings()
