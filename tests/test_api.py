"""Tests for the Chess Lab HTTP API."""

from pathlib import Path

import chess
from fastapi.testclient import TestClient
import pytest

from backend.app import app, get_storage
from chesslab.storage import SQLiteGameStorage


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "normal_game.pgn"
client = TestClient(app)


def test_practice_positions_save_reopen_edit_and_remove(storage: SQLiteGameStorage, tmp_path: Path) -> None:
    user_id = storage.get_or_create_user_for_identity(display_name="Alice", platform="lichess", username="Alice")
    other_id = storage.get_or_create_user_for_identity(display_name="Charlie", platform="lichess", username="Charlie")
    pgn = FIXTURE_PATH.read_text(encoding="utf-8").replace('[Site "Local"]', '[Site "https://lichess.org/aB3dE5gH"]')
    assert client.post('/api/games/import', files={"file": ("game.pgn", pgn)}).status_code == 200
    path = f"/api/users/{user_id}/practice-positions"
    payload = {"family": "King's Pawn Game", "player_color": "white", "line": ["e7e5"],
               "date_from": "2026.08.01", "note": "  Develop the bishop  ", "candidate_move": " Bc4 "}
    response = client.post(path, json=payload)
    assert response.status_code == 200
    assert response.json()["created"] is True
    saved = response.json()["position"]
    assert saved["san_path"] == ["e4", "e5"]
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    assert saved["fen"] == board.fen()
    assert saved["note"] == "Develop the bishop"
    assert saved["candidate_move"] == "Bc4"
    assert saved["examples"][0]["source_url"] == "https://lichess.org/aB3dE5gH"
    assert client.get(path).json() == [saved]
    reopened = client.get(f"/api/users/{user_id}/openings/explorer", params={
        "family": saved["family"], "color": saved["player_color"], "line": ','.join(saved["line"]),
        "date_from": saved["date_from"],
    })
    assert reopened.json()["fen"] == saved["fen"]
    # Independent storage connections retain saved entries and existing games.
    persisted = SQLiteGameStorage(tmp_path / "test.db").list_practice_positions(user_id)
    assert persisted[0]["fen"] == saved["fen"]
    duplicate = client.post(path, json={**payload, "note": "Do not overwrite"}).json()
    assert duplicate == {"created": False, "position": saved}
    # A repeated position with different clocks also deduplicates.
    cycle = ["e7e5", "g1f3", "g8f6", "f3g1", "f6g8"]
    assert client.post(path, json={**payload, "line": cycle}).json() == duplicate
    other_path = f"/api/users/{other_id}/practice-positions"
    assert client.get(other_path).json() == []
    assert client.patch(f"{other_path}/{saved['id']}", json={"note": "Wrong user"}).status_code == 404
    assert client.delete(f"{other_path}/{saved['id']}").status_code == 404
    update = client.patch(f"{path}/{saved['id']}", json={"note": " Try knight first ", "candidate_move": "Nf3"})
    assert update.status_code == 200
    assert update.json()["note"] == "Try knight first"
    assert client.get(path).json()[0]["candidate_move"] == "Nf3"
    assert client.delete(f"{path}/{saved['id']}").status_code == 204
    assert client.get(path).json() == []
    assert client.get('/api/games').json()["total"] == 1


def test_practice_positions_validate_without_writing(storage: SQLiteGameStorage) -> None:
    user_id = storage.get_or_create_user_for_identity(display_name="Alice", platform="lichess", username="Alice")
    path = f"/api/users/{user_id}/practice-positions"
    payload = {"family": "King's Pawn Game", "player_color": "white", "line": ["e7e5"]}
    for invalid in ({"candidate_move": "Qh6"}, {"candidate_move": "--"}, {"line": ["e2e4"]},
                    {"line": ["0000"]}, {"note": "x" * 1001}, {"player_color": "green"}):
        assert client.post(path, json={**payload, **invalid}).status_code == 422
    assert client.post(path, json={**payload, "family": "Unknown opening"}).status_code == 404
    assert client.post('/api/users/9999/practice-positions', json=payload).status_code == 404
    assert client.get('/api/users/9999/practice-positions').status_code == 404
    assert client.get(path).json() == []
    saved = client.post(path, json=payload).json()["position"]
    assert saved["note"] == saved["candidate_move"] == ""
    assert saved["examples"] == []
    assert client.patch(f"{path}/{saved['id']}", json={"candidate_move": "--"}).status_code == 422
    assert client.get(path).json() == [saved]
    black = client.post(path, json={**payload, "player_color": "black"}).json()
    assert black["created"] is True
    assert black["position"]["id"] != saved["id"]


def test_opening_explorer_scopes_archive_and_validates_moves(storage: SQLiteGameStorage) -> None:
    user_id = storage.get_or_create_user_for_identity(display_name="Alice", platform="lichess", username="Alice")
    other_id = storage.get_or_create_user_for_identity(display_name="Charlie", platform="lichess", username="Charlie")
    pgn = FIXTURE_PATH.read_text(encoding="utf-8").replace('[Site "Local"]', '[Site "https://lichess.org/aB3dE5gH"]')
    assert client.post('/api/games/import', files={"file": ("game.pgn", pgn)}).status_code == 200
    path = f"/api/users/{user_id}/openings/explorer"
    query = {"family": "King's Pawn Game", "color": "white"}
    result = client.get(path, params=query)
    assert result.status_code == 200
    assert result.json()["games"] == 1
    assert result.json()["moves"][0]["san"] == "e5"
    # e4 appears in this game even if its final opening label is more specific.
    assert result.json()["san_path"] == ["e4"]
    assert client.get(path, params={**query, "color": "black"}).json()["games"] == 0
    assert client.get(path, params={**query, "date_from": "2026.08.28"}).json()["games"] == 0
    assert client.get(path, params={**query, "date_to": "2026.08.26"}).json()["games"] == 0
    assert client.get(f"/api/users/{other_id}/openings/explorer", params=query).json()["games"] == 0
    assert client.get(path, params={**query, "line": "e7e5"}).json()["moves"][0]["san"] == "Bc4"
    assert client.get(path, params={**query, "line": "0000"}).status_code == 422
    assert client.get(path, params={**query, "line": "z9z8"}).status_code == 422
    assert client.get(path, params={**query, "family": "Not an opening"}).status_code == 404
    assert client.get('/api/users/9999/openings/explorer', params=query).status_code == 404


@pytest.fixture
def storage(tmp_path: Path, monkeypatch) -> SQLiteGameStorage:
    test_storage = SQLiteGameStorage(tmp_path / "test.db")
    app.dependency_overrides[get_storage] = lambda: test_storage
    monkeypatch.setattr("backend.app.get_principal", lambda request: None)
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

    second_pgn = (
        lichess_pgn.replace("aB3dE5gH", "iJ4kL6mN")
        .replace('[Date "2026.08.27"]', '[Date "2026.08.28"]')
        .replace('[Result "1-0"]', '[Result "0-1"]')
        .replace("4. Qxf7# 1-0", "4. Qxf7# 0-1")
    )
    second_import = client.post(
        "/api/games/import",
        files={"file": ("second_lichess.pgn", second_pgn, "application/x-chess-pgn")},
    )
    assert second_import.status_code == 200

    overview_response = client.get(f"/api/users/{user_id}/overview")
    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview == {
        "user": {
            "id": user_id,
            "display_name": "Alice",
            "identities": [{"platform": "lichess", "username": "Alice"}],
        },
        "total_games": 2,
        "white_games": 2,
        "black_games": 0,
        "wins": 1,
        "draws": 0,
        "losses": 1,
        "classified_games": 2,
        "first_game_date": "2026.08.27",
        "last_game_date": "2026.08.28",
        "minimum_rating": 1500,
        "maximum_rating": 1500,
        "top_openings": [
            {
                "eco": "C20",
                "opening": "King's Pawn Game",
                "games": 2,
                "wins": 1,
                "draws": 0,
                "losses": 1,
                "moves": ["e4"],
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
    assert (detail["games"], detail["wins"], detail["draws"], detail["losses"]) == (2, 1, 0, 1)
    assert detail["colors"] == [
        {"color": "white", "games": 2, "wins": 1, "draws": 0, "losses": 1}
    ]
    assert detail["variations"] == [
        {
            "eco": "C20",
            "opening": "King's Pawn Game",
            "games": 2,
            "wins": 1,
            "draws": 0,
            "losses": 1,
            "moves": ["e4"],
        }
    ]
    assert detail["years"] == [
        {"year": "2026", "games": 2, "wins": 1, "draws": 0, "losses": 1}
    ]
    assert detail["recent_games"][0]["player_color"] == "white"

    responses_response = client.get(f"/api/users/{user_id}/responses")
    assert responses_response.status_code == 200
    assert responses_response.json() == [
        {"reply": "e5", "games": 2, "wins": 1, "draws": 0, "losses": 1}
    ]

    adjusted_response = client.get(
        f"/api/users/{user_id}/openings/adjusted", params={"min_games": 2}
    )
    assert adjusted_response.status_code == 200
    adjusted = adjusted_response.json()[0]
    assert adjusted["opening"] == "King's Pawn Game"
    assert adjusted["color"] == "white"
    assert adjusted["games"] == 2
    assert adjusted["actual_score"] == pytest.approx(0.5)
    assert adjusted["moves"] == ["e4"]
    assert adjusted["expected_score"] == pytest.approx(0.5714631174)
    assert adjusted["adjusted_score"] == pytest.approx(-0.0714631174)
    assert adjusted["reliability"] == "limited"

    practice_response = client.get(
        f"/api/users/{user_id}/openings/practice",
        params={"family": "King's Pawn Game"},
    )
    assert practice_response.status_code == 200
    assert practice_response.json()["moves"] == ["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6"]
    assert practice_response.json()["lichess_url"].endswith("/e4_e5_Bc4_Nc6_Qh5_Nf6")


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

    item_id = response.json()[0]["id"]
    update_response = client.patch(
        f"/api/users/{user_id}/repertoire/{item_id}",
        json={
            "context": "As Black vs 1.d4",
            "opening": "Slav Defense",
            "status": "try",
            "note": "Try this next.",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["opening"] == "Slav Defense"

    delete_response = client.delete(f"/api/users/{user_id}/repertoire/{item_id}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/users/{user_id}/repertoire").json() == []
