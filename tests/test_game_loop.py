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
    monkeypatch.setenv("QUESTION_TIME_LIMIT", "0.5")
    monkeypatch.setattr(runner_module, "REVEAL_SECONDS", 0.05)
    for cached in (get_settings, get_store, get_manager, get_runners):
        cached.cache_clear()
    yield
    for cached in (get_settings, get_store, get_manager, get_runners):
        cached.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def host(client):
    return client.post(
        "/rooms", json={"host_name": "Alice", "question_count": 2}
    ).json()


def drain_until(ws, wanted: str, limit: int = 12) -> dict:
    for _ in range(limit):
        message = ws.receive_json()
        if message["type"] == wanted:
            return message
    raise AssertionError(f"never received {wanted!r}")


def test_non_host_cannot_start(client, host):
    code = host["room_code"]
    bob = client.post(f"/rooms/{code}/join", json={"name": "Bob"}).json()

    with client.websocket_connect(f"/ws/{code}?token={bob['token']}") as ws:
        ws.receive_json()
        ws.send_json({"type": "start"})
        assert ws.receive_json()["type"] == "error"


def test_question_start_hides_the_answer(client, host):
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as ws:
        ws.receive_json()
        ws.send_json({"type": "start"})
        message = drain_until(ws, "question_start")

    assert "correct_index" not in message["payload"]
    assert len(message["payload"]["options"]) >= 2
    assert message["payload"]["total"] == 2


def test_answering_ends_the_question_early(client, host):
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as ws:
        ws.receive_json()
        ws.send_json({"type": "start"})
        drain_until(ws, "question_start")

        ws.send_json({"type": "answer", "option_index": 0})
        assert drain_until(ws, "answer_received")

        end = drain_until(ws, "question_end")

    assert "correct_index" in end["payload"]
    assert len(end["payload"]["answers"]) == 1


def test_question_ends_on_timeout_without_answers(client, host):
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as ws:
        ws.receive_json()
        ws.send_json({"type": "start"})
        drain_until(ws, "question_start")

        end = drain_until(ws, "question_end")

    assert end["payload"]["answers"] == []


def test_full_game_reaches_game_over(client, host):
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as ws:
        ws.receive_json()
        ws.send_json({"type": "start"})

        over = drain_until(ws, "game_over", limit=30)

    assert over["payload"]["leaderboard"][0]["name"] == "Alice"


def test_answer_outside_a_question_is_rejected(client, host):
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as ws:
        ws.receive_json()
        ws.send_json({"type": "answer", "option_index": 0})
        assert ws.receive_json()["type"] == "error"


def test_starting_twice_is_rejected(client, host):
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as ws:
        ws.receive_json()
        ws.send_json({"type": "start"})
        drain_until(ws, "question_start")

        ws.send_json({"type": "start"})
        error = drain_until(ws, "error")

    assert "already" in error["payload"]["detail"].lower()