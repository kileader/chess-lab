"""Tests for local SQLite game persistence."""

from pathlib import Path

from chesslab.models import GameRecord
from chesslab.storage import SQLiteGameStorage


def test_storage_persists_games_between_connections(tmp_path: Path) -> None:
    database_path = tmp_path / "games.db"
    game = GameRecord(
        date="2026.08.27",
        white="Alice",
        black="Bob",
        white_elo=1500,
        black_elo=1450,
        result="1-0",
        time_control="600+5",
        eco="C20",
        opening="King's Pawn Game",
        opening_ply=None,
        move_count=4,
        site="https://lichess.org/aB3dE5gH",
        source="lichess",
        source_url="https://lichess.org/aB3dE5gH",
        source_game_id="aB3dE5gH",
        pgn='[Site "https://lichess.org/aB3dE5gH"]\n\n1. e4 *\n',
        fingerprint="test-fingerprint",
    )

    assert SQLiteGameStorage(database_path).save_games([game]) == 1
    assert SQLiteGameStorage(database_path).save_games([game]) == 0

    assert SQLiteGameStorage(database_path).list_games() == [game]
    assert SQLiteGameStorage(database_path).count_games() == 1
    assert SQLiteGameStorage(database_path).list_games(limit=1, offset=1) == []

    user_id = SQLiteGameStorage(database_path).get_or_create_user_for_identity(
        display_name="Alice",
        platform="lichess",
        username="Alice",
    )
    overview = SQLiteGameStorage(database_path).get_user_overview(user_id)
    assert overview is not None
    assert overview["total_games"] == 1
    assert overview["wins"] == 1
