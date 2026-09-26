"""Tests for position-based ECO opening classification."""

from io import StringIO
from pathlib import Path

import chess.pgn

from chesslab.openings import OpeningCatalog


OPENINGS_PATH = Path(__file__).parents[1] / "data" / "openings"


def test_catalog_classifies_a_transposable_opening_position() -> None:
    catalog = OpeningCatalog.from_directory(OPENINGS_PATH)
    game = chess.pgn.read_game(StringIO("1. e4 e5 2. Nf3 Nc6 3. Bb5 *"))
    assert game is not None

    match = catalog.classify_game(game)

    assert match is not None
    assert match.eco == "C60"
    assert match.name == "Ruy Lopez"
    assert match.ply == 5


def test_catalog_returns_canonical_moves_for_an_opening_family() -> None:
    catalog = OpeningCatalog.from_directory(OPENINGS_PATH)

    assert catalog.moves_for_name("Philidor Defense") == [
        "e4", "e5", "Nf3", "d6"
    ]


def test_catalog_resolves_a_named_london_line_from_its_family_root() -> None:
    catalog = OpeningCatalog.from_directory(OPENINGS_PATH)

    assert catalog.continuation_for_name(
        "Indian Defense", "Indian Defense: Accelerated London System"
    ) == ["c1f4"]
    assert catalog.continuation_for_name(
        "Queen's Pawn Game", "Queen's Pawn Game: London System"
    ) == ["d7d5", "g1f3", "g8f6", "c1f4"]
    assert catalog.continuation_for_name(
        "Indian Defense", "Queen's Pawn Game: London System"
    ) is None
