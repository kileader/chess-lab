"""Load chess games from PGN files."""

from pathlib import Path

import chess.pgn


def load_games(path: Path) -> list[chess.pgn.Game]:
    """Load every game in a PGN file."""
    games: list[chess.pgn.Game] = []

    with path.open(encoding="utf-8") as pgn_file:
        while True:
            game = chess.pgn.read_game(pgn_file)
            if game is None:
                break
            games.append(game)

    return games
