from functools import lru_cache

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings


@lru_cache
def get_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )


def init_db() -> None:
    import app.models_db  # noqa: F401 — registers the tables

    SQLModel.metadata.create_all(get_engine())


def new_session() -> Session:
    return Session(get_engine())