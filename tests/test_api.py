"""Tests for the Chess Lab HTTP API."""

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.app import app, get_storage
from chesslab.storage import SQLiteGameStorage


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "normal_game.pgn"
client = TestClient(app)


@pytest.fixture
def storage(tmp_path: Path) -> SQLiteGameStorage:
    test_storage = SQLiteGameStorage(tmp_path / "test.db")
    app.dependency_overrides[get_storage] = lambda: test_storage
    yield test_storage
    app.dependency_overrides.clear()


def test_import_games_accepts_pgn_upload(storage: SQLiteGameStorage) -> None:
    with FIXTURE_PATH.open("rb") as pgn_file:
        response = client.post(
            "/api/games/import",
            files={"file": ("normal_game.pgn", pgn_file, "application/x-chess-pgn")},
        )

    assert response.status_code == 200
    assert response.json() == {
        "games_received": 1,
        "games_added": 1,
        "duplicates_skipped": 0,
    }

    with FIXTURE_PATH.open("rb") as pgn_file:
        duplicate_response = client.post(
            "/api/games/import",
            files={"file": ("normal_game.pgn", pgn_file, "application/x-chess-pgn")},
        )

    assert duplicate_response.json() == {
        "games_received": 1,
        "games_added": 0,
        "duplicates_skipped": 1,
    }

    stored_response = client.get("/api/games")
    assert stored_response.status_code == 200
    assert stored_response.json() == {
        "total": 1,
        "limit": 50,
        "offset": 0,
        "games": [
            {
                "date": "2026.08.27",
                "white": "Alice",
                "black": "Bob",
                "white_elo": 1500,
                "black_elo": 1450,
                "result": "1-0",
                "time_control": "600+5",
                "eco": "C20",
                "opening": "King's Pawn Game",
                "opening_ply": None,
                "move_count": 4,
                "site": "Local",
                "source": "other",
                "source_url": "Local",
                "source_game_id": None,
            }
        ],
    }


def test_user_overview_uses_linked_platform_identity(
    storage: SQLiteGameStorage,
) -> None:
    user_response = client.post(
        "/api/users",
        json={
            "display_name": "Alice",
            "platform": "lichess",
            "username": "Alice",
        },
    )
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]

    lichess_pgn = FIXTURE_PATH.read_text(encoding="utf-8").replace(
        '[Site "Local"]',
        '[Site "https://lichess.org/aB3dE5gH"]',
    )
    import_response = client.post(
        "/api/games/import",
        files={"file": ("lichess.pgn", lichess_pgn, "application/x-chess-pgn")},
    )
    assert import_response.status_code == 200

    overview_response = client.get(f"/api/users/{user_id}/overview")
    assert overview_response.status_code == 200
    assert overview_response.json() == {
        "user": {
            "id": user_id,
            "display_name": "Alice",
            "identities": [{"platform": "lichess", "username": "Alice"}],
        },
        "total_games": 1,
        "white_games": 1,
        "black_games": 0,
        "wins": 1,
        "draws": 0,
        "losses": 0,
        "classified_games": 1,
        "first_game_date": "2026.08.27",
        "last_game_date": "2026.08.27",
        "minimum_rating": 1500,
        "maximum_rating": 1500,
        "top_openings": [
            {
                "eco": "C20",
                "opening": "King's Pawn Game",
                "games": 1,
                "wins": 1,
                "draws": 0,
                "losses": 0,
            }
        ],
    }

    detail_response = client.get(
        f"/api/users/{user_id}/openings/detail",
        params={"family": "King's Pawn Game"},
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["family"] == "King's Pawn Game"
    assert (detail["games"], detail["wins"], detail["draws"], detail["losses"]) == (1, 1, 0, 0)
    assert detail["colors"] == [
        {"color": "white", "games": 1, "wins": 1, "draws": 0, "losses": 0}
    ]
    assert detail["variations"] == [
        {
            "eco": "C20",
            "opening": "King's Pawn Game",
            "games": 1,
            "wins": 1,
            "draws": 0,
            "losses": 0,
        }
    ]
    assert detail["years"] == [
        {"year": "2026", "games": 1, "wins": 1, "draws": 0, "losses": 0}
    ]
    assert detail["recent_games"][0]["player_color"] == "white"


def test_user_repertoire_is_saved_per_user(storage: SQLiteGameStorage) -> None:
    user_response = client.post(
        "/api/users",
        json={"display_name": "Alice", "platform": "lichess", "username": "Alice"},
    )
    user_id = user_response.json()["id"]

    response = client.post(
        f"/api/users/{user_id}/repertoire",
        json=[
            {
                "context": "As Black vs 1.e4",
                "opening": "Caro-Kann Defense",
                "status": "keep",
                "note": "Established answer.",
            }
        ],
    )

    assert response.status_code == 200
    assert response.json()[0] == {
        "id": 1,
        "context": "As Black vs 1.e4",
        "opening": "Caro-Kann Defense",
        "status": "keep",
        "note": "Established answer.",
    }
    assert client.get(f"/api/users/{user_id}/repertoire").json() == response.json()
