import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import get_store


@pytest.fixture(autouse=True)
def fresh_store():
    get_store.cache_clear()
    yield
    get_store.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def create_room(client, host="Alice", count=3):
    return client.post(
        "/rooms", json={"host_name": host, "question_count": count}
    )


def test_create_room_returns_code_and_token(client):
    res = create_room(client)
    assert res.status_code == 201

    body = res.json()
    assert len(body["room_code"]) == 6
    assert body["token"]
    assert body["player"]["is_host"] is True


def test_second_player_joins(client):
    code = create_room(client).json()["room_code"]

    res = client.post(f"/rooms/{code}/join", json={"name": "Bob"})

    assert res.status_code == 200
    assert res.json()["player"]["is_host"] is False


def test_room_code_is_case_insensitive(client):
    code = create_room(client).json()["room_code"]

    res = client.post(f"/rooms/{code.lower()}/join", json={"name": "Bob"})

    assert res.status_code == 200


def test_duplicate_name_returns_409(client):
    code = create_room(client, host="Alice").json()["room_code"]

    res = client.post(f"/rooms/{code}/join", json={"name": "alice"})

    assert res.status_code == 409
    assert res.json()["error"] == "NameTaken"


def test_unknown_room_returns_404(client):
    res = client.post("/rooms/ZZZZZZ/join", json={"name": "Bob"})

    assert res.status_code == 404


def test_blank_name_is_rejected(client):
    res = client.post("/rooms", json={"host_name": "   "})

    assert res.status_code == 422


def test_room_view_hides_answers(client):
    code = create_room(client).json()["room_code"]

    body = client.get(f"/rooms/{code}").json()

    assert "questions" not in body
    assert body["phase"] == "lobby"
    assert body["players"][0]["name"] == "Alice"
    assert "id" not in body["players"][0]


def test_tokens_are_unique_per_player(client):
    first = create_room(client).json()
    code = first["room_code"]
    second = client.post(f"/rooms/{code}/join", json={"name": "Bob"}).json()

    assert first["token"] != second["token"]