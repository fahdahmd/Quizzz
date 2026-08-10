import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings

_ALL_LIMITERS: list["RateLimiter"] = []


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Leftmost entry is the original client.
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Fixed-window limiter keyed by client IP. Per-process only."""

    def __init__(self, times: int, seconds: float, name: str) -> None:
        self.times = times
        self.seconds = seconds
        self.name = name
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        _ALL_LIMITERS.append(self)

    async def __call__(self, request: Request) -> None:
        key = client_ip(request)
        now = time.monotonic()

        hits = self._hits[key]
        while hits and now - hits[0] > self.seconds:
            hits.popleft()

        if len(hits) >= self.times:
            raise HTTPException(
                status_code=429,
                detail=f"too many {self.name} requests",
                headers={"Retry-After": str(int(self.seconds))},
            )

        hits.append(now)

        if len(self._hits) > 5000:
            self._prune(now)

    def _prune(self, now: float) -> None:
        stale = [k for k, v in self._hits.items() if not v or now - v[-1] > self.seconds]
        for k in stale:
            del self._hits[k]

    def reset(self) -> None:
        self._hits.clear()


def reset_all_limiters() -> None:
    for limiter in _ALL_LIMITERS:
        limiter.reset()