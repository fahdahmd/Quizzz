from dataclasses import dataclass
from enum import Enum


class GamePhase(str, Enum):
    LOBBY = "lobby"
    QUESTION = "question"
    REVEAL = "reveal"
    FINISHED = "finished"


@dataclass(frozen=True)
class Question:
    text: str
    options: list[str]
    correct_index: int

    def __post_init__(self) -> None:
        if len(self.options) < 2:
            raise ValueError("a question needs at least two options")
        if not 0 <= self.correct_index < len(self.options):
            raise ValueError("correct_index is out of range")


@dataclass
class Player:
    id: str
    name: str
    score: int = 0
    is_host: bool = False


@dataclass(frozen=True)
class Answer:
    player_id: str
    option_index: int
    elapsed: float
    is_correct: bool
    points: int