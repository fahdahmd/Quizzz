import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repository import game_detail, recent_games, save_finished_game
from engine.game import Room
from engine.models import Question


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def finished_room() -> Room:
    questions = [
        Question("Q1?", ["a", "b", "c", "d"], 1),
        Question("Q2?", ["a", "b", "c", "d"], 0),
    ]
    room = Room("ABC123", questions, topic="Cricket")
    alice = room.add_player("Alice")
    bob = room.add_player("Bob")

    room.start()
    room.submit_answer(alice.id, 1, elapsed=1.0)
    room.submit_answer(bob.id, 0, elapsed=1.0)
    room.reveal()
    room.next_question()
    room.submit_answer(alice.id, 0, elapsed=1.0)
    room.reveal()
    room.next_question()
    return room


def test_finished_game_is_saved_with_ranks():
    game_id = save_finished_game(finished_room())

    detail = game_detail(game_id)

    assert detail["topic"] == "Cricket"
    assert detail["question_count"] == 2
    assert [r["rank"] for r in detail["results"]] == [1, 2]
    assert detail["results"][0]["name"] == "Alice"


def test_recent_games_reports_the_winner():
    save_finished_game(finished_room())

    games = recent_games()

    assert len(games) == 1
    assert games[0]["winner"] == "Alice"
    assert games[0]["player_count"] == 2


def test_games_endpoints(client):
    game_id = save_finished_game(finished_room())

    listing = client.get("/games")
    detail = client.get(f"/games/{game_id}")

    assert listing.status_code == 200
    assert listing.json()[0]["room_code"] == "ABC123"
    assert detail.json()["results"][0]["score"] > 0


def test_unknown_game_is_404(client):
    assert client.get("/games/9999").status_code == 404


def test_rate_limit_kicks_in(client, monkeypatch):
    from app.routers import rooms as rooms_router

    monkeypatch.setattr(rooms_router.create_limit, "times", 3)

    codes = [
        client.post("/rooms", json={"host_name": f"P{i}"}).status_code
        for i in range(4)
    ]

    assert codes[:3] == [201, 201, 201]
    assert codes[3] == 429


def test_forged_forwarded_header_is_ignored_by_default(client, monkeypatch):
    from app.routers import rooms as rooms_router

    monkeypatch.setattr(rooms_router.create_limit, "times", 2)

    codes = []
    for i in range(3):
        res = client.post(
            "/rooms",
            json={"host_name": f"P{i}"},
            headers={"X-Forwarded-For": f"10.0.0.{i}"},
        )
        codes.append(res.status_code)

    # Spoofing a new IP each time must not reset the limit.
    assert codes == [201, 201, 429]


def test_forwarded_header_is_used_when_trusted(client, monkeypatch):
    from app.config import get_settings
    from app.routers import rooms as rooms_router

    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(rooms_router.create_limit, "times", 1)

    first = client.post(
        "/rooms", json={"host_name": "A"}, headers={"X-Forwarded-For": "10.0.0.1"}
    )
    second = client.post(
        "/rooms", json={"host_name": "B"}, headers={"X-Forwarded-For": "10.0.0.2"}
    )

    assert first.status_code == 201
    assert second.status_code == 201


def test_responses_carry_a_request_id(client):
    res = client.get("/health")

    assert len(res.headers["X-Request-ID"]) == 12


def test_internal_errors_are_opaque(client, monkeypatch):
    from app.routers import rooms as rooms_router

    def boom(count):
        raise RuntimeError("database on fire at /secret/path/config.py")

    monkeypatch.setattr(rooms_router, "pick_questions", boom)

    res = client.post("/rooms", json={"host_name": "Alice"})
    body = res.json()

    assert res.status_code == 500
    assert body["error"] == "InternalError"
    assert "secret" not in str(body)
    assert "request_id" in body