import pytest
from revoice.config import settings
from revoice.database.migrations import run_migrations


@pytest.fixture(autouse=True, scope="session")
async def setup_test_db():
    settings.ensure_dirs()
    await run_migrations()
