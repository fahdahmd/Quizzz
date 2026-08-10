import pytest

from app.ai.generator import get_generator
from app.config import get_settings
from app.db import get_engine, init_db
from app.ratelimit import reset_all_limiters
from app.store import get_store
from app.ws.manager import get_manager
from app.ws.runner import get_runners

CACHES = (get_settings, get_store, get_manager, get_runners, get_generator, get_engine)


@pytest.fixture(autouse=True)
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")

    for cached in CACHES:
        cached.cache_clear()
    reset_all_limiters()
    init_db()

    yield

    reset_all_limiters()
    for cached in CACHES:
        cached.cache_clear()