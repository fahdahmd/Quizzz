import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.store import get_store
from app.ws.manager import get_manager


@pytest.fixture(autouse=True)
def fresh_state():
    get_store.cache_clear()
    get_manager.cache_clear()
    yield
    get_store.cache_clear()
    get_manager.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def host(client):
    return client.post(
        "/rooms", json={"host_name": "Alice", "question_count": 3}
    ).json()


def test_valid_token_receives_room_state(client, host):
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as ws:
        message = ws.receive_json()

    assert message["type"] == "room_state"
    assert message["payload"]["code"] == host["room_code"]
    assert message["payload"]["players"][0]["name"] == "Alice"


def test_bad_token_is_rejected(client, host):
    url = f"/ws/{host['room_code']}?token=totally-invalid-token"

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url) as ws:
            ws.receive_json()


def test_token_from_other_room_is_rejected(client, host):
    other = client.post("/rooms", json={"host_name": "Bob"}).json()
    url = f"/ws/{host['room_code']}?token={other['token']}"

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url) as ws:
            ws.receive_json()


def test_existing_player_is_notified_of_a_join(client, host):
    code = host["room_code"]

    with client.websocket_connect(f"/ws/{code}?token={host['token']}") as alice:
        alice.receive_json()  # room_state

        bob = client.post(f"/rooms/{code}/join", json={"name": "Bob"}).json()
        with client.websocket_connect(f"/ws/{code}?token={bob['token']}") as bob_ws:
            bob_ws.receive_json()  # room_state

            event = alice.receive_json()

    assert event["type"] == "player_joined"
    assert event["payload"]["name"] == "Bob"


def test_ping_gets_pong(client, host):
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as ws:
        ws.receive_json()
        ws.send_json({"type": "ping"})
        reply = ws.receive_json()

    assert reply["type"] == "pong"


def test_unknown_message_type_gets_an_error(client, host):
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as ws:
        ws.receive_json()
        ws.send_json({"type": "launch_missiles"})
        reply = ws.receive_json()

    assert reply["type"] == "error"


def test_malformed_json_does_not_kill_the_connection(client, host):
    url = f"/ws/{host['room_code']}?token={host['token']}"

    with client.websocket_connect(url) as ws:
        ws.receive_json()
        ws.send_text("{not json")
        assert ws.receive_json()["type"] == "error"

        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"