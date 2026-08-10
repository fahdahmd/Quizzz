from engine.game import Room
from engine.models import Answer, GamePhase, Question


def room_state(
    room: Room,
    connected: set[str],
    remaining: float | None = None,
    viewer_id: str | None = None,
) -> dict:
    payload: dict = {
        "code": room.code,
        "phase": room.phase.value,
        "question_count": len(room.questions),
        "current_index": room.current_index,
        "players": [
            {
                "name": p.name,
                "score": p.score,
                "is_host": p.is_host,
                "connected": p.id in connected,
            }
            for p in room.leaderboard()
        ],
    }

    if room.phase is GamePhase.QUESTION and remaining is not None:
        question = room.current_question
        payload["question"] = {
            "index": room.current_index,
            "text": question.text,
            "options": question.options,
            "remaining": round(remaining, 2),
        }
        payload["you_answered"] = viewer_id in room.answers

    if viewer_id in room.players:
        me = room.players[viewer_id]
        payload["you"] = {
            "name": me.name,
            "score": me.score,
            "is_host": me.is_host,
        }

    return {"type": "room_state", "payload": payload}


def player_event(event: str, name: str) -> dict:
    return {"type": event, "payload": {"name": name}}


def error(detail: str) -> dict:
    return {"type": "error", "payload": {"detail": detail}}

def question_start(
    index: int, total: int, question: Question, time_limit: float
) -> dict:
    return {
        "type": "question_start",
        "payload": {
            "index": index,
            "total": total,
            "text": question.text,
            "options": question.options,
            "time_limit": time_limit,
        },
    }

def _leaderboard(room: Room) -> list[dict]:
    return [
        {"name": p.name, "score": p.score} for p in room.leaderboard()
    ]


def question_end(room: Room, question: Question, answers: list[Answer]) -> dict:
    return {
        "type": "question_end",
        "payload": {
            "correct_index": question.correct_index,
            "answers": [
                {
                    "name": room.players[a.player_id].name,
                    "option_index": a.option_index,
                    "is_correct": a.is_correct,
                    "points": a.points,
                }
                for a in answers
            ],
            "leaderboard": _leaderboard(room),
        },
    }


def game_over(room: Room) -> dict:
    return {
        "type": "game_over",
        "payload": {"leaderboard": _leaderboard(room)},
    }