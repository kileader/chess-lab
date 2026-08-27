"""Tests for the Chess Lab HTTP API."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "normal_game.pgn"
client = TestClient(app)


def test_import_games_accepts_pgn_upload() -> None:
    with FIXTURE_PATH.open("rb") as pgn_file:
        response = client.post(
            "/api/games/import",
            files={"file": ("normal_game.pgn", pgn_file, "application/x-chess-pgn")},
        )

    assert response.status_code == 200
    assert response.json() == {
        "games_loaded": 1,
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
                "move_count": 4,
            }
        ],
    }
