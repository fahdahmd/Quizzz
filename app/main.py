import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db
from app.routers import games, rooms, ws
from app.store import RoomNotFound, ServerBusy, get_store
from app.ws.manager import get_manager
from app.ws.runner import get_runners
from engine.game import (
    AlreadyAnswered,
    GameError,
    NameTaken,
    RoomFull,
    UnknownPlayer,
    WrongPhase,
)

logger = logging.getLogger(__name__)

SWEEP_INTERVAL = 60.0
ROOM_MAX_IDLE = 1800.0  # 30 minutes

settings = get_settings()


def sweep_once() -> list[str]:
    """Deletes rooms that are idle and have nobody connected."""
    store = get_store()
    manager = get_manager()
    runners = get_runners()

    swept = []
    for code in store.idle_codes(ROOM_MAX_IDLE):
        if manager.connected_ids(code):
            store.touch(code)  # still in use, just quiet
            continue
        runners.remove(code)
        store.delete_room(code)
        swept.append(code)

    if swept:
        logger.info("swept %d idle room(s): %s", len(swept), ", ".join(swept))
    return swept


async def _sweeper_loop() -> None:
    while True:
        await asyncio.sleep(SWEEP_INTERVAL)
        try:
            sweep_once()
        except Exception:
            logger.exception("room sweep failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )
    init_db()

    task = asyncio.create_task(_sweeper_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="Quiz Game API", version="0.6.0", lifespan=lifespan)

app.include_router(rooms.router)
app.include_router(ws.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid4().hex[:12]
    request.state.request_id = request_id

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "unhandled error [%s] %s %s",
            request_id,
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "InternalError", "request_id": request_id},
        )

    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(games.router)

STATUS_BY_ERROR: dict[type[Exception], int] = {
    RoomNotFound: 404,
    UnknownPlayer: 404,
    RoomFull: 409,
    NameTaken: 409,
    WrongPhase: 409,
    AlreadyAnswered: 409,
    ServerBusy: 503,
}


def _handle(exc: Exception) -> JSONResponse:
    status = STATUS_BY_ERROR.get(type(exc), 400)
    return JSONResponse(
        status_code=status,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


@app.exception_handler(GameError)
def game_error_handler(request: Request, exc: GameError) -> JSONResponse:
    return _handle(exc)


@app.exception_handler(StoreError := RoomNotFound.__base__)
def store_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return _handle(exc)


@app.exception_handler(ValueError)
def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": "ValueError", "detail": str(exc)},
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "env": settings.app_env,
        "rooms": get_store().room_count,
    }