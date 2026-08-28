"""Tests for PGN metadata conversion."""

from pathlib import Path
from textwrap import dedent

import chess.pgn

from chesslab.importer import game_to_record, load_game_records, parse_game_records
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
            opening_ply=None,
            move_count=4,
            site="Local",
            source="other",
            source_url="Local",
            source_game_id=None,
            pgn=records[0].pgn,
            fingerprint=records[0].fingerprint,
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
        opening_ply=None,
        move_count=0,
        site=None,
        source="other",
        source_url=None,
        source_game_id=None,
        pgn=game_to_record(game).pgn,
        fingerprint=game_to_record(game).fingerprint,
    )


def test_game_to_record_identifies_lichess_provenance() -> None:
    game = chess.pgn.Game()
    game.headers["Site"] = "https://lichess.org/aB3dE5gHzzzz"
    game.headers["White"] = "ChessLabUser"
    game.headers["Black"] = "Opponent"

    record = game_to_record(game)

    assert record.source == "lichess"
    assert record.source_url == "https://lichess.org/aB3dE5gHzzzz"
    assert record.source_game_id == "aB3dE5gH"
    assert record.pgn.endswith("*\n")


def test_game_to_record_identifies_chess_com_link() -> None:
    pgn = dedent(
        '''
        [Event "Live Chess"]
        [Site "Chess.com"]
        [Date "2026.08.27"]
        [White "Alice"]
        [Black "Bob"]
        [Result "1-0"]
        [Link "https://www.chess.com/game/live/123456789"]

        1. e4 e5 2. Bc4 1-0
        '''
    )

    record = parse_game_records(pgn)[0]

    assert record.source == "chess_com"
    assert record.source_url == "https://www.chess.com/game/live/123456789"
    assert record.source_game_id == "123456789"
    assert "1. e4 e5 2. Bc4 1-0" in record.pgn
