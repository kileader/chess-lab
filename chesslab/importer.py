"""Load chess games from PGN files."""

from pathlib import Path

import chess.pgn


def load_first_game(path: Path) -> chess.pgn.Game | None:
    """Load the first game in a PGN file, or return None if it is empty."""
    with path.open(encoding="utf-8") as pgn_file:
        return chess.pgn.read_game(pgn_file)
