from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GameRecord(SQLModel, table=True):
    __tablename__ = "games"

    id: int | None = Field(default=None, primary_key=True)
    room_code: str = Field(index=True, max_length=12)
    topic: str | None = Field(default=None, max_length=60)
    question_count: int
    player_count: int
    finished_at: datetime = Field(default_factory=utcnow, index=True)


class PlayerResult(SQLModel, table=True):
    __tablename__ = "player_results"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    name: str = Field(max_length=20)
    score: int
    rank: int