"""Tests for PGN metadata conversion."""

from pathlib import Path

import chess.pgn

from chesslab.importer import game_to_record, load_game_records
from chesslab.models import GameRecord


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "normal_game.pgn"


def test_load_game_records_extracts_metadata() -> None:
    records = load_game_records(FIXTURE_PATH)

    assert records == [
        GameRecord(
            date="2026.08.27",
            white="Alice",
            black="Bob",
            white_elo=1500,
            black_elo=1450,
            result="1-0",
            time_control="600+5",
            eco="C20",
            opening="King's Pawn Game",
            move_count=4,
        )
    ]


def test_game_to_record_handles_missing_and_invalid_headers() -> None:
    game = chess.pgn.Game()
    game.headers["WhiteElo"] = "not-rated"

    assert game_to_record(game) == GameRecord(
        date=None,
        white=None,
        black=None,
        white_elo=None,
        black_elo=None,
        result=None,
        time_control=None,
        eco=None,
        opening=None,
        move_count=0,
    )
