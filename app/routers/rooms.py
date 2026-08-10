from fastapi import APIRouter, Depends

from app.ai.generator import QuestionGenerator, get_generator
from app.config import get_settings
from app.ratelimit import RateLimiter
from app.schemas import (
    CreateRoomRequest,
    JoinResponse,
    JoinRoomRequest,
    PlayerOut,
    PublicPlayer,
    RoomOut,
)
from app.store import RoomStore, get_store
from engine.bank import pick_questions
from engine.game import Room

router = APIRouter(prefix="/rooms", tags=["rooms"])

settings = get_settings()

create_limit = RateLimiter(settings.rate_limit_create, 60.0, "room creation")
join_limit = RateLimiter(settings.rate_limit_join, 60.0, "join")


def _room_out(room: Room) -> RoomOut:
    return RoomOut(
        code=room.code,
        phase=room.phase.value,
        question_count=len(room.questions),
        current_index=room.current_index,
        players=[
            PublicPlayer(name=p.name, score=p.score, is_host=p.is_host)
            for p in room.leaderboard()
        ],
    )


@router.post(
    "",
    status_code=201,
    response_model=JoinResponse,
    dependencies=[Depends(create_limit)],
)
async def create_room(
    payload: CreateRoomRequest,
    store: RoomStore = Depends(get_store),
    generator: QuestionGenerator = Depends(get_generator),
) -> JoinResponse:
    if payload.topic:
        questions, source = await generator.generate(
            payload.topic, payload.question_count
        )
    else:
        questions, source = pick_questions(payload.question_count), "bank"

    room = store.create_room(questions, topic=payload.topic)
    host = room.add_player(payload.host_name)
    token = store.issue_token(room.code, host.id)

    return JoinResponse(
        room_code=room.code,
        token=token,
        player=PlayerOut(**vars(host)),
        question_source=source,
    )


@router.post(
    "/{code}/join",
    response_model=JoinResponse,
    dependencies=[Depends(join_limit)],
)
def join_room(
    code: str,
    payload: JoinRoomRequest,
    store: RoomStore = Depends(get_store),
) -> JoinResponse:
    room = store.get_room(code)
    player = room.add_player(payload.name)
    token = store.issue_token(room.code, player.id)

    return JoinResponse(
        room_code=room.code,
        token=token,
        player=PlayerOut(**vars(player)),
    )


@router.get("/{code}", response_model=RoomOut)
def read_room(
    code: str,
    store: RoomStore = Depends(get_store),
) -> RoomOut:
    return _room_out(store.get_room(code))