import pytest

from engine.game import (
    AlreadyAnswered,
    NameTaken,
    Room,
    RoomFull,
    UnknownPlayer,
    WrongPhase,
)
from engine.models import GamePhase, Question


@pytest.fixture
def questions() -> list[Question]:
    return [
        Question("Capital of Japan?", ["Osaka", "Tokyo", "Kyoto"], 1),
        Question("2 + 2 = ?", ["3", "4", "5"], 1),
    ]


@pytest.fixture
def room(questions) -> Room:
    return Room(code="ABC123", questions=questions, time_limit=20.0)


def test_first_player_becomes_host(room):
    alice = room.add_player("Alice")
    bob = room.add_player("Bob")

    assert alice.is_host is True
    assert bob.is_host is False
    assert room.host_id == alice.id


def test_duplicate_name_is_rejected(room):
    room.add_player("Alice")
    with pytest.raises(NameTaken):
        room.add_player("alice")


def test_room_respects_max_players(questions):
    room = Room("ABC123", questions, max_players=2)
    room.add_player("Alice")
    room.add_player("Bob")
    with pytest.raises(RoomFull):
        room.add_player("Carol")


def test_cannot_join_after_start(room):
    room.add_player("Alice")
    room.start()
    with pytest.raises(WrongPhase):
        room.add_player("Bob")


def test_faster_correct_answer_scores_higher(room):
    alice = room.add_player("Alice")
    bob = room.add_player("Bob")
    room.start()

    fast = room.submit_answer(alice.id, 1, elapsed=2.0)
    slow = room.submit_answer(bob.id, 1, elapsed=15.0)

    assert fast.is_correct and slow.is_correct
    assert fast.points > slow.points


def test_wrong_answer_scores_zero(room):
    alice = room.add_player("Alice")
    room.start()

    answer = room.submit_answer(alice.id, 0, elapsed=1.0)

    assert answer.is_correct is False
    assert answer.points == 0
    assert room.players[alice.id].score == 0


def test_late_answer_scores_zero(room):
    alice = room.add_player("Alice")
    room.start()

    answer = room.submit_answer(alice.id, 1, elapsed=25.0)

    assert answer.points == 0


def test_double_answer_is_rejected(room):
    alice = room.add_player("Alice")
    room.start()
    room.submit_answer(alice.id, 1, elapsed=1.0)

    with pytest.raises(AlreadyAnswered):
        room.submit_answer(alice.id, 1, elapsed=2.0)


def test_unknown_player_cannot_answer(room):
    room.add_player("Alice")
    room.start()

    with pytest.raises(UnknownPlayer):
        room.submit_answer("not-a-real-id", 1, elapsed=1.0)


def test_full_game_reaches_finished(room):
    alice = room.add_player("Alice")
    room.start()

    room.submit_answer(alice.id, 1, elapsed=1.0)
    room.reveal()
    assert room.next_question() is not None

    room.submit_answer(alice.id, 1, elapsed=1.0)
    room.reveal()
    assert room.next_question() is None
    assert room.phase is GamePhase.FINISHED


def test_leaderboard_is_sorted_by_score(room):
    alice = room.add_player("Alice")
    bob = room.add_player("Bob")
    room.start()

    room.submit_answer(alice.id, 0, elapsed=1.0)   # wrong
    room.submit_answer(bob.id, 1, elapsed=1.0)     # correct

    board = room.leaderboard()
    assert board[0].name == "Bob"
    assert board[1].name == "Alice"


def test_answer_inside_the_grace_window_still_scores(room):
    alice = room.add_player("Alice")
    room.start()

    answer = room.submit_answer(alice.id, 1, elapsed=20.4)

    assert answer.is_correct is True
    assert answer.points > 0


def test_answer_beyond_the_grace_window_scores_zero(room):
    alice = room.add_player("Alice")
    room.start()

    answer = room.submit_answer(alice.id, 1, elapsed=21.5)

    assert answer.points == 0


def test_answered_all_of_ignores_absent_players(room):
    alice = room.add_player("Alice")
    bob = room.add_player("Bob")
    room.start()
    room.submit_answer(alice.id, 1, elapsed=1.0)

    assert room.answered_all_of({alice.id, bob.id}) is False
    assert room.answered_all_of({alice.id}) is True