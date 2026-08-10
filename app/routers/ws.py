import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.store import RoomNotFound, RoomStore, get_store
from app.ws.manager import get_manager
from app.ws.protocol import error, player_event, room_state
from app.ws.runner import get_runners
from engine.game import GameError, Player, Room

router = APIRouter()

MAX_MESSAGE_BYTES = 4096

CLOSE_BAD_ORIGIN = 4403
CLOSE_BAD_TOKEN = 4401
CLOSE_REPLACED = 4409


def _authenticate(
    code: str, token: str, store: RoomStore
) -> tuple[Room, Player] | None:
    resolved = store.resolve_token(token)
    if resolved is None:
        return None

    token_code, player_id = resolved
    if token_code.upper() != code.strip().upper():
        return None

    try:
        room = store.get_room(code)
    except RoomNotFound:
        return None

    player = room.players.get(player_id)
    if player is None:
        return None

    return room, player


@router.websocket("/ws/{code}")
async def game_socket(
    websocket: WebSocket,
    code: str,
    token: str = Query(..., min_length=10, max_length=200),
) -> None:
    settings = get_settings()
    store = get_store()
    manager = get_manager()
    runners = get_runners()

    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.origins:
        await websocket.close(code=CLOSE_BAD_ORIGIN)
        return

    auth = _authenticate(code, token, store)
    if auth is None:
        await websocket.close(code=CLOSE_BAD_TOKEN)
        return

    room, player = auth
    code = room.code

    await websocket.accept()

    previous = await manager.connect(code, player.id, websocket)
    if previous is not None:
        try:
            await previous.close(code=CLOSE_REPLACED)
        except Exception:
            pass

    store.touch(code)
    runner = runners.find(code)

    await manager.send(
        websocket,
        room_state(
            room,
            manager.connected_ids(code),
            remaining=runner.remaining() if runner else None,
            viewer_id=player.id,
        ),
    )
    await manager.broadcast(
        code,
        player_event(
            "player_reconnected" if previous is not None else "player_joined",
            player.name,
        ),
        exclude=player.id,
    )

    try:
        while True:
            raw = await websocket.receive_text()
            store.touch(code)

            if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                await manager.send(websocket, error("message too large"))
                continue

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send(websocket, error("invalid JSON"))
                continue

            if not isinstance(message, dict):
                await manager.send(websocket, error("message must be an object"))
                continue

            match message.get("type"):
                case "ping":
                    await manager.send(websocket, {"type": "pong", "payload": {}})

                case "state":
                    active = runners.find(code)
                    await manager.send(
                        websocket,
                        room_state(
                            room,
                            manager.connected_ids(code),
                            remaining=active.remaining() if active else None,
                            viewer_id=player.id,
                        ),
                    )

                case "start":
                    if not player.is_host:
                        await manager.send(
                            websocket, error("only the host can start the game")
                        )
                    else:
                        try:
                            runners.get_or_create(room, manager).start()
                        except GameError as exc:
                            await manager.send(websocket, error(str(exc)))

                case "answer":
                    runner = runners.find(code)
                    option = message.get("option_index")

                    if not isinstance(option, int):
                        await manager.send(
                            websocket, error("option_index must be an integer")
                        )
                    elif runner is None or not runner.question_open:
                        await manager.send(websocket, error("no question is open"))
                    else:
                        try:
                            await runner.submit(player.id, option)
                        except (GameError, ValueError) as exc:
                            await manager.send(websocket, error(str(exc)))
                        else:
                            await manager.send(
                                websocket, {"type": "answer_received", "payload": {}}
                            )

                case unknown:
                    await manager.send(websocket, error(f"unknown type: {unknown!r}"))

    except WebSocketDisconnect:
        pass
    finally:
        was_registered = await manager.disconnect(code, player.id, websocket)

        if was_registered:
            await manager.broadcast(code, player_event("player_left", player.name))

            active = runners.find(code)
            if active is not None:
                active.note_disconnect()

            if not manager.connected_ids(code):
                runners.remove(code)