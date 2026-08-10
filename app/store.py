import secrets
import time
from functools import lru_cache

from app.config import get_settings
from engine.game import Room
from engine.models import Question

# No O/0, I/1 — codes get read aloud and typed by hand.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class StoreError(Exception):
    pass


class RoomNotFound(StoreError):
    pass


class ServerBusy(StoreError):
    pass


class RoomStore:
    def __init__(
        self,
        *,
        code_length: int = 6,
        max_players: int = 20,
        time_limit: float = 20.0,
        max_rooms: int = 500,
    ) -> None:
        self.code_length = code_length
        self.max_players = max_players
        self.time_limit = time_limit
        self.max_rooms = max_rooms

        self._rooms: dict[str, Room] = {}
        self._tokens: dict[str, tuple[str, str]] = {}
        self._activity: dict[str, float] = {}

    def _new_code(self) -> str:
        for _ in range(10):
            code = "".join(
                secrets.choice(CODE_ALPHABET) for _ in range(self.code_length)
            )
            if code not in self._rooms:
                return code
        raise ServerBusy("could not allocate a unique room code")

    def create_room(self, questions: list[Question], topic: str | None = None) -> Room:
        if len(self._rooms) >= self.max_rooms:
            raise ServerBusy("too many active rooms")

        code = self._new_code()
        room = Room(
            code=code,
            questions=questions,
            time_limit=self.time_limit,
            max_players=self.max_players,
            topic=topic,
        )
        self._rooms[code] = room
        self._activity[code] = time.monotonic()
        return room

    def get_room(self, code: str) -> Room:
        room = self._rooms.get(code.strip().upper())
        if room is None:
            raise RoomNotFound(code)
        return room

    def issue_token(self, code: str, player_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self._tokens[token] = (code, player_id)
        return token

    def resolve_token(self, token: str) -> tuple[str, str] | None:
        return self._tokens.get(token)

    def touch(self, code: str) -> None:
        if code in self._rooms:
            self._activity[code] = time.monotonic()

    def idle_codes(self, max_idle: float) -> list[str]:
        now = time.monotonic()
        return [c for c, seen in self._activity.items() if now - seen > max_idle]

    def delete_room(self, code: str) -> None:
        self._rooms.pop(code, None)
        self._activity.pop(code, None)
        # Tokens outlive their room otherwise — a slow memory leak.
        for token, (token_code, _) in list(self._tokens.items()):
            if token_code == code:
                del self._tokens[token]

    @property
    def room_count(self) -> int:
        return len(self._rooms)


@lru_cache
def get_store() -> RoomStore:
    settings = get_settings()
    return RoomStore(
        code_length=settings.room_code_length,
        max_players=settings.max_players_per_room,
        time_limit=settings.question_time_limit,
    )