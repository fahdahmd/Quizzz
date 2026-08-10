import asyncio
import logging
from functools import lru_cache

from app.repository import save_finished_game
from app.ws.manager import ConnectionManager
from app.ws.protocol import error, game_over, question_end, question_start
from engine.game import Room, WrongPhase

logger = logging.getLogger(__name__)

REVEAL_SECONDS = 4.0


class GameRunner:
    """Owns the clock for one room."""

    def __init__(self, room: Room, manager: ConnectionManager) -> None:
        self.room = room
        self.manager = manager
        self._task: asyncio.Task | None = None
        self._all_answered = asyncio.Event()
        self._started_at: float | None = None
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def question_open(self) -> bool:
        return self._started_at is not None

    def start(self) -> None:
        if self.running:
            raise WrongPhase("the game is already running")
        self._task = asyncio.create_task(self._run())

    def cancel(self) -> None:
        if self.running:
            self._task.cancel()

    def elapsed(self) -> float:
        if self._started_at is None:
            raise WrongPhase("no question is currently open")
        return asyncio.get_running_loop().time() - self._started_at

    def remaining(self) -> float | None:
        if self._started_at is None:
            return None
        elapsed = asyncio.get_running_loop().time() - self._started_at
        return max(0.0, self.room.time_limit - elapsed)

    async def submit(self, player_id: str, option_index: int) -> None:
        async with self._lock:
            if self._started_at is None:
                raise WrongPhase("no question is open")
            elapsed = asyncio.get_running_loop().time() - self._started_at
            self.room.submit_answer(player_id, option_index, elapsed)

        self._wake_if_all_answered()

    def note_disconnect(self) -> None:
        self._wake_if_all_answered()

    def _wake_if_all_answered(self) -> None:
        connected = self.manager.connected_ids(self.room.code)
        if self.room.answered_all_of(connected):
            self._all_answered.set()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        code = self.room.code

        try:
            question = self.room.start()

            while question is not None:
                self._all_answered.clear()
                self._started_at = loop.time()

                await self.manager.broadcast(
                    code,
                    question_start(
                        index=self.room.current_index,
                        total=len(self.room.questions),
                        question=question,
                        time_limit=self.room.time_limit,
                    ),
                )

                try:
                    await asyncio.wait_for(
                        self._all_answered.wait(), timeout=self.room.time_limit
                    )
                except asyncio.TimeoutError:
                    pass

                async with self._lock:
                    self._started_at = None
                    answers = self.room.reveal()

                await self.manager.broadcast(
                    code, question_end(self.room, question, answers)
                )

                await asyncio.sleep(REVEAL_SECONDS)
                question = self.room.next_question()

            await self.manager.broadcast(code, game_over(self.room))

            try:
                # SQLModel is synchronous — a thread keeps the write off the loop.
                await asyncio.to_thread(save_finished_game, self.room)
            except Exception:
                logger.exception("failed to persist game %s", code)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("game loop crashed in room %s", code)
            self._started_at = None
            await self.manager.broadcast(code, error("the game ended unexpectedly"))


class RunnerRegistry:
    def __init__(self) -> None:
        self._runners: dict[str, GameRunner] = {}

    def get_or_create(self, room: Room, manager: ConnectionManager) -> GameRunner:
        runner = self._runners.get(room.code)
        if runner is None:
            runner = GameRunner(room, manager)
            self._runners[room.code] = runner
        return runner

    def find(self, code: str) -> GameRunner | None:
        return self._runners.get(code)

    def remove(self, code: str) -> None:
        runner = self._runners.pop(code, None)
        if runner is not None:
            runner.cancel()


@lru_cache
def get_runners() -> RunnerRegistry:
    return RunnerRegistry()