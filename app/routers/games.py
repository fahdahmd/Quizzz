from fastapi import APIRouter, HTTPException, Query

from app.repository import game_detail, recent_games

router = APIRouter(prefix="/games", tags=["games"])


@router.get("")
def list_games(limit: int = Query(10, ge=1, le=50)) -> list[dict]:
    return recent_games(limit)


@router.get("/{game_id}")
def read_game(game_id: int) -> dict:
    detail = game_detail(game_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="game not found")
    return detail