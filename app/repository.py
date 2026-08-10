from sqlmodel import desc, select

from app.db import new_session
from app.models_db import GameRecord, PlayerResult
from engine.game import Room


def save_finished_game(room: Room) -> int:
    with new_session() as session:
        record = GameRecord(
            room_code=room.code,
            topic=room.topic,
            question_count=len(room.questions),
            player_count=len(room.players),
        )
        session.add(record)
        session.commit()
        session.refresh(record)

        for rank, player in enumerate(room.leaderboard(), start=1):
            session.add(
                PlayerResult(
                    game_id=record.id,
                    name=player.name,
                    score=player.score,
                    rank=rank,
                )
            )
        session.commit()
        return record.id


def recent_games(limit: int = 10) -> list[dict]:
    with new_session() as session:
        games = session.exec(
            select(GameRecord).order_by(desc(GameRecord.finished_at)).limit(limit)
        ).all()

        results = []
        for game in games:
            winner = session.exec(
                select(PlayerResult)
                .where(PlayerResult.game_id == game.id, PlayerResult.rank == 1)
            ).first()
            results.append(
                {
                    "id": game.id,
                    "room_code": game.room_code,
                    "topic": game.topic,
                    "question_count": game.question_count,
                    "player_count": game.player_count,
                    "finished_at": game.finished_at,
                    "winner": winner.name if winner else None,
                }
            )
        return results


def game_detail(game_id: int) -> dict | None:
    with new_session() as session:
        game = session.get(GameRecord, game_id)
        if game is None:
            return None

        players = session.exec(
            select(PlayerResult)
            .where(PlayerResult.game_id == game_id)
            .order_by(PlayerResult.rank)
        ).all()

        return {
            "id": game.id,
            "room_code": game.room_code,
            "topic": game.topic,
            "question_count": game.question_count,
            "finished_at": game.finished_at,
            "results": [
                {"rank": p.rank, "name": p.name, "score": p.score} for p in players
            ],
        }