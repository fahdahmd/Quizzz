import re

from pydantic import BaseModel, Field, field_validator

NAME_RE = re.compile(r"^[\w \-']+$", re.UNICODE)
TOPIC_RE = re.compile(r"^[\w \-'&,.?]+$", re.UNICODE)


class CreateRoomRequest(BaseModel):
    host_name: str = Field(min_length=1, max_length=20)
    question_count: int = Field(default=5, ge=1, le=20)
    topic: str | None = Field(default=None, max_length=60)

    @field_validator("host_name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("topic")
    @classmethod
    def clean_topic(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if "\n" in v or "\r" in v:
            raise ValueError("topic must be a single line")
        if not TOPIC_RE.match(v):
            raise ValueError("topic contains unsupported characters")
        return v


class JoinRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return _validate_name(v)


def _validate_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("name cannot be blank")
    if not NAME_RE.match(v):
        raise ValueError("name may only contain letters, digits, spaces, - and '")
    return v


class PlayerOut(BaseModel):
    id: str
    name: str
    score: int
    is_host: bool


class PublicPlayer(BaseModel):
    name: str
    score: int
    is_host: bool


class JoinResponse(BaseModel):
    room_code: str
    token: str
    player: PlayerOut
    question_source: str | None = None


class RoomOut(BaseModel):
    code: str
    phase: str
    question_count: int
    current_index: int
    players: list[PublicPlayer]