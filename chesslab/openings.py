"""Position-based ECO opening classification."""

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import chess
import chess.pgn


@dataclass(frozen=True)
class OpeningMatch:
    """The deepest named opening position reached by a game."""

    eco: str
    name: str
    ply: int


class OpeningCatalog:
    """Look up opening names by board position to support transpositions."""

    def __init__(
        self,
        positions: dict[str, tuple[str, str]],
        move_lines: dict[str, tuple[str, ...]],
    ) -> None:
        self._positions = positions
        self._move_lines = move_lines

    @classmethod
    def from_directory(cls, directory: Path) -> "OpeningCatalog":
        """Load the five Lichess ECO TSV volumes from a local directory."""
        positions: dict[str, tuple[str, str]] = {}
        move_lines: dict[str, tuple[str, ...]] = {}

        for volume in "abcde":
            path = directory / f"{volume}.tsv"
            with path.open(encoding="utf-8", newline="") as opening_file:
                for row in csv.DictReader(opening_file, delimiter="\t"):
                    game = chess.pgn.read_game(StringIO(row["pgn"]))
                    if game is None:
                        continue
                    board = game.board()
                    san_moves: list[str] = []
                    for move in game.mainline_moves():
                        san_moves.append(board.san(move))
                        board.push(move)
                    positions[board.epd()] = (row["eco"], row["name"])
                    existing_line = move_lines.get(row["name"])
                    if existing_line is None or len(san_moves) < len(existing_line):
                        move_lines[row["name"]] = tuple(san_moves)

        return cls(positions, move_lines)

    def moves_for_name(self, name: str) -> list[str]:
        """Return a canonical SAN move line for an opening or opening family."""
        exact = self._move_lines.get(name)
        if exact is not None:
            return list(exact)

        family_prefix = f"{name}:"
        family_lines = [
            moves
            for opening_name, moves in self._move_lines.items()
            if opening_name.startswith(family_prefix)
        ]
        if not family_lines:
            return []
        return list(min(family_lines, key=len))

    def classify_game(self, game: chess.pgn.Game) -> OpeningMatch | None:
        """Return the last known opening position reached on the main line."""
        board = game.board()
        match: OpeningMatch | None = None

        for ply, move in enumerate(game.mainline_moves(), start=1):
            board.push(move)
            opening = self._positions.get(board.epd())
            if opening is not None:
                eco, name = opening
                match = OpeningMatch(eco=eco, name=name, ply=ply)

        return match

    def classify_pgn(self, pgn: str) -> OpeningMatch | None:
        """Parse and classify one complete PGN string."""
        game = chess.pgn.read_game(StringIO(pgn))
        if game is None:
            return None
        return self.classify_game(game)
