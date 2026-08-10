import asyncio
from functools import lru_cache

from fastapi import WebSocket


class ConnectionManager:
    """Tracks live sockets per room. Knows nothing about game rules."""

    def __init__(self) -> None:
        self._rooms: dict[str, dict[str, WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self, code: str, player_id: str, ws: WebSocket
    ) -> WebSocket | None:
        """Registers ws. Returns the player's previous socket, if any."""
        async with self._lock:
            room = self._rooms.setdefault(code, {})
            previous = room.get(player_id)
            room[player_id] = ws
        return previous

    async def disconnect(self, code: str, player_id: str, ws: WebSocket) -> bool:
        """Returns True only if this socket was still the registered one."""
        async with self._lock:
            room = self._rooms.get(code)
            if room is None:
                return False

            removed = False
            if room.get(player_id) is ws:
                room.pop(player_id, None)
                removed = True

            if not room:
                self._rooms.pop(code, None)

            return removed

    async def send(self, ws: WebSocket, message: dict) -> None:
        await ws.send_json(message)

    async def broadcast(
        self, code: str, message: dict, exclude: str | None = None
    ) -> None:
        async with self._lock:
            targets = [
                (pid, ws)
                for pid, ws in self._rooms.get(code, {}).items()
                if pid != exclude
            ]

        for player_id, ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(code, player_id, ws)

    def connected_ids(self, code: str) -> set[str]:
        return set(self._rooms.get(code, {}))


@lru_cache
def get_manager() -> ConnectionManager:
    return ConnectionManager()