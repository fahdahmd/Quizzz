import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app, sweep_once
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


def test_reconnect_mid_question_restores_the_question(client):
    host = client.post(
        "/rooms", json={"host_name": "Alice", "question_count": 2}
    ).json()
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as first:
        first.receive_json()
        first.send_json({"type": "start"})
        drain_until(first, "question_start")

        with client.websocket_connect(url) as second:
            snapshot = second.receive_json()

    payload = snapshot["payload"]

    assert payload["phase"] == "question"
    assert payload["question"]["remaining"] > 0
    assert payload["you_answered"] is False
    assert "correct_index" not in payload["question"]
    assert payload["you"]["name"] == "Alice"


def test_reconnect_shows_already_answered(client):
    host = client.post(
        "/rooms", json={"host_name": "Alice", "question_count": 2}
    ).json()
    code = host["room_code"]
    bob = client.post(f"/rooms/{code}/join", json={"name": "Bob"}).json()
    bob_url = f"/ws/{code}?token={bob['token']}"

    with client.websocket_connect(f"/ws/{code}?token={host['token']}") as alice:
        alice.receive_json()

        with client.websocket_connect(bob_url) as bob_ws:
            bob_ws.receive_json()
            alice.send_json({"type": "start"})
            drain_until(bob_ws, "question_start")
            bob_ws.send_json({"type": "answer", "option_index": 0})
            drain_until(bob_ws, "answer_received")

            with client.websocket_connect(bob_url) as bob_again:
                snapshot = bob_again.receive_json()

    assert snapshot["payload"]["you_answered"] is True


def test_others_see_a_reconnect_not_a_departure(client):
    host = client.post("/rooms", json={"host_name": "Alice"}).json()
    code = host["room_code"]
    bob = client.post(f"/rooms/{code}/join", json={"name": "Bob"}).json()
    bob_url = f"/ws/{code}?token={bob['token']}"

    with client.websocket_connect(f"/ws/{code}?token={host['token']}") as alice:
        alice.receive_json()

        with client.websocket_connect(bob_url) as bob_ws:
            bob_ws.receive_json()
            assert drain_until(alice, "player_joined")["payload"]["name"] == "Bob"

            with client.websocket_connect(bob_url) as bob_again:
                bob_again.receive_json()
                event = alice.receive_json()

    assert event["type"] == "player_reconnected"


def test_sweeper_removes_idle_rooms_and_their_tokens(client, monkeypatch):
    import app.main as main

    host = client.post("/rooms", json={"host_name": "Alice"}).json()
    code = host["room_code"]
    store = get_store()

    monkeypatch.setattr(main, "ROOM_MAX_IDLE", -1.0)  # everything is idle

    swept = sweep_once()

    assert code in swept
    assert store.resolve_token(host["token"]) is None
    assert client.get(f"/rooms/{code}").status_code == 404


def test_sweeper_spares_rooms_with_live_connections(client, monkeypatch):
    import app.main as main

    host = client.post("/rooms", json={"host_name": "Alice"}).json()
    code = host["room_code"]

    monkeypatch.setattr(main, "ROOM_MAX_IDLE", -1.0)

    with client.websocket_connect(f"/ws/{code}?token={host['token']}") as ws:
        ws.receive_json()
        swept = sweep_once()

    assert code not in swept
    assert client.get(f"/rooms/{code}").status_code == 200