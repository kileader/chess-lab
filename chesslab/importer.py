"""Load chess games from PGN files."""

from io import StringIO
from pathlib import Path
from typing import TextIO

import chess.pgn

from chesslab.models import GameRecord


MISSING_HEADER_VALUES = {"", "?", "*", "????.??.??"}


def _clean_header(game: chess.pgn.Game, name: str) -> str | None:
    """Return a trimmed header value, or None when it is missing."""
    value = game.headers.get(name)
    if value is None:
        return None

    cleaned_value = value.strip()
    if cleaned_value in MISSING_HEADER_VALUES:
        return None

    return cleaned_value


def _parse_elo(value: str | None) -> int | None:
    """Convert a rating header to an integer when possible."""
    if value is None:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def game_to_record(game: chess.pgn.Game) -> GameRecord:
    """Convert a parsed python-chess game into clean Chess Lab metadata."""
    ply_count = sum(1 for _ in game.mainline_moves())

    return GameRecord(
        date=_clean_header(game, "Date"),
        white=_clean_header(game, "White"),
        black=_clean_header(game, "Black"),
        white_elo=_parse_elo(_clean_header(game, "WhiteElo")),
        black_elo=_parse_elo(_clean_header(game, "BlackElo")),
        result=_clean_header(game, "Result"),
        time_control=_clean_header(game, "TimeControl"),
        eco=_clean_header(game, "ECO"),
        opening=_clean_header(game, "Opening"),
        move_count=(ply_count + 1) // 2,
    )


def _read_games(pgn_file: TextIO) -> list[chess.pgn.Game]:
    """Read every game from an open PGN text stream."""
    games: list[chess.pgn.Game] = []

    while True:
        game = chess.pgn.read_game(pgn_file)
        if game is None:
            break
        games.append(game)

    return games


def load_games(path: Path) -> list[chess.pgn.Game]:
    """Load every game from a PGN file path."""
    with path.open(encoding="utf-8") as pgn_file:
        return _read_games(pgn_file)


def parse_game_records(pgn_text: str) -> list[GameRecord]:
    """Parse PGN text into structured Chess Lab records."""
    with StringIO(pgn_text) as pgn_file:
        games = _read_games(pgn_file)

    return [game_to_record(game) for game in games]


def load_game_records(path: Path) -> list[GameRecord]:
    """Load every game in a PGN file as structured Chess Lab records."""
    return [game_to_record(game) for game in load_games(path)]
