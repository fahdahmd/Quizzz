import uuid

from engine.models import Answer, GamePhase, Player, Question


class GameError(Exception):
    """Base class for every rule the engine enforces."""


class RoomFull(GameError):
    pass


class NameTaken(GameError):
    pass


class WrongPhase(GameError):
    pass


class UnknownPlayer(GameError):
    pass


class AlreadyAnswered(GameError):
    pass


BASE_POINTS = 1000
SPEED_WEIGHT = 0.5
LATE_TOLERANCE = 0.75

class Room:
    def __init__(
        self,
        code: str,
        questions: list[Question],
        time_limit: float = 20.0,
        max_players: int = 20,
        topic: str | None = None,
        late_tolerance: float = LATE_TOLERANCE,
    ) -> None:
        if not questions:
            raise ValueError("a room needs at least one question")

        self.code = code
        self.questions = questions
        self.time_limit = time_limit
        self.max_players = max_players
        self.topic = topic
        self.late_tolerance = late_tolerance

        self.players: dict[str, Player] = {}
        self.host_id: str | None = None
        self.phase = GamePhase.LOBBY
        self.current_index = -1
        self.answers: dict[str, Answer] = {}

    # ---------- lobby ----------

    def add_player(self, name: str) -> Player:
        name = name.strip()
        if not name:
            raise ValueError("name cannot be empty")
        if self.phase is not GamePhase.LOBBY:
            raise WrongPhase("players can only join from the lobby")
        if len(self.players) >= self.max_players:
            raise RoomFull(f"room {self.code} is full")
        if any(p.name.lower() == name.lower() for p in self.players.values()):
            raise NameTaken(name)

        player = Player(
            id=uuid.uuid4().hex,
            name=name,
            is_host=not self.players,
        )
        self.players[player.id] = player
        if player.is_host:
            self.host_id = player.id
        return player

    # ---------- game flow ----------

    def start(self) -> Question:
        if self.phase is not GamePhase.LOBBY:
            raise WrongPhase("the game has already started")
        if not self.players:
            raise WrongPhase("cannot start an empty room")

        self.phase = GamePhase.QUESTION
        self.current_index = 0
        self.answers = {}
        return self.current_question

    @property
    def current_question(self) -> Question:
        if not 0 <= self.current_index < len(self.questions):
            raise WrongPhase("no question is active")
        return self.questions[self.current_index]

    @property
    def everyone_answered(self) -> bool:
        return len(self.answers) == len(self.players)
    
    def answered_all_of(self, player_ids: set[str]) -> bool:
        """True when every player in player_ids has answered."""
        active = player_ids & set(self.players)
        if not active:
            return False
        return all(pid in self.answers for pid in active)

    def submit_answer(
        self, player_id: str, option_index: int, elapsed: float
    ) -> Answer:
        if self.phase is not GamePhase.QUESTION:
            raise WrongPhase("answers are only accepted while a question is open")
        if player_id not in self.players:
            raise UnknownPlayer(player_id)
        if player_id in self.answers:
            raise AlreadyAnswered(player_id)

        question = self.current_question
        if not 0 <= option_index < len(question.options):
            raise ValueError("option_index is out of range")
        if elapsed < 0:
            raise ValueError("elapsed cannot be negative")

        if elapsed > self.time_limit + self.late_tolerance:
            is_correct, points = False, 0
        else:
            is_correct = option_index == question.correct_index
            # Answers inside the grace window score as if they landed
            # exactly on the deadline — the minimum for a correct answer.
            points = self._score(min(elapsed, self.time_limit)) if is_correct else 0

        answer = Answer(player_id, option_index, elapsed, is_correct, points)
        self.answers[player_id] = answer
        self.players[player_id].score += points
        return answer

    def _score(self, elapsed: float) -> int:
        fraction_used = min(elapsed / self.time_limit, 1.0)
        return round(BASE_POINTS * (1 - SPEED_WEIGHT * fraction_used))

    def reveal(self) -> list[Answer]:
        if self.phase is not GamePhase.QUESTION:
            raise WrongPhase("there is no open question to reveal")
        self.phase = GamePhase.REVEAL
        return list(self.answers.values())

    def next_question(self) -> Question | None:
        if self.phase is not GamePhase.REVEAL:
            raise WrongPhase("reveal the current question first")

        if self.current_index + 1 >= len(self.questions):
            self.phase = GamePhase.FINISHED
            return None

        self.current_index += 1
        self.answers = {}
        self.phase = GamePhase.QUESTION
        return self.current_question

    def leaderboard(self) -> list[Player]:
        return sorted(
            self.players.values(),
            key=lambda p: (-p.score, p.name.lower()),
        )