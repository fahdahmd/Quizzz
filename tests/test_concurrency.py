import time

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.store import get_store
from app.ws import runner as runner_module
from app.ws.manager import get_manager
from app.ws.runner import get_runners


@pytest.fixture(autouse=True)
def fast_game(monkeypatch):
    monkeypatch.setenv("QUESTION_TIME_LIMIT", "3.0")
    monkeypatch.setattr(runner_module, "REVEAL_SECONDS", 0.05)
    for cached in (get_settings, get_store, get_manager, get_runners):
        cached.cache_clear()
    yield
    for cached in (get_settings, get_store, get_manager, get_runners):
        cached.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def drain_until(ws, wanted: str, limit: int = 12) -> dict:
    for _ in range(limit):
        message = ws.receive_json()
        if message["type"] == wanted:
            return message
    raise AssertionError(f"never received {wanted!r}")


def test_simultaneous_answers_each_count_once(client):
    host = client.post(
        "/rooms", json={"host_name": "P0", "question_count": 1}
    ).json()
    code = host["room_code"]

    tokens = [host["token"]]
    for i in range(1, 5):
        joined = client.post(f"/rooms/{code}/join", json={"name": f"P{i}"}).json()
        tokens.append(joined["token"])

    sockets = []
    try:
        for token in tokens:
            ws = client.websocket_connect(f"/ws/{code}?token={token}").__enter__()
            ws.receive_json()
            sockets.append(ws)

        sockets[0].send_json({"type": "start"})
        for ws in sockets:
            drain_until(ws, "question_start")

        # Fire everything before reading anything.
        for ws in sockets:
            ws.send_json({"type": "answer", "option_index": 1})

        end = drain_until(sockets[0], "question_end", limit=20)
    finally:
        for ws in sockets:
            ws.__exit__(None, None, None)

    names = [a["name"] for a in end["payload"]["answers"]]

    assert len(names) == 5
    assert len(set(names)) == 5
    assert len(end["payload"]["leaderboard"]) == 5


def test_double_answer_scores_once(client):
    host = client.post(
        "/rooms", json={"host_name": "Alice", "question_count": 1}
    ).json()
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as ws:
        ws.receive_json()
        ws.send_json({"type": "start"})
        drain_until(ws, "question_start")

        ws.send_json({"type": "answer", "option_index": 1})
        ws.send_json({"type": "answer", "option_index": 2})

        end = drain_until(ws, "question_end", limit=20)

    assert len(end["payload"]["answers"]) == 1


def test_disconnected_player_does_not_stall_the_question(client):
    host = client.post(
        "/rooms", json={"host_name": "Alice", "question_count": 1}
    ).json()
    code = host["room_code"]
    bob = client.post(f"/rooms/{code}/join", json={"name": "Bob"}).json()

    with client.websocket_connect(f"/ws/{code}?token={host['token']}") as alice:
        alice.receive_json()

        with client.websocket_connect(f"/ws/{code}?token={bob['token']}") as bob_ws:
            bob_ws.receive_json()
            alice.receive_json()  # player_joined

            alice.send_json({"type": "start"})
            drain_until(alice, "question_start")
            drain_until(bob_ws, "question_start")

        # Bob's socket is now closed; Alice answers alone.
        started = time.monotonic()
        alice.send_json({"type": "answer", "option_index": 1})
        drain_until(alice, "question_end", limit=20)
        took = time.monotonic() - started

    # Would be ~3s if the room waited out the timer for Bob.
    assert took < 2.0