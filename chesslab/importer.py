"""Load chess games from PGN files."""

from hashlib import sha256
from io import StringIO
from pathlib import Path
import re
from collections.abc import Iterator
from typing import TextIO
from urllib.parse import urlparse

import chess.pgn

from chesslab.models import GameRecord, GameSource
from chesslab.openings import OpeningCatalog


MISSING_HEADER_VALUES = {"", "?", "*", "????.??.??"}
LICHESS_GAME_ID = re.compile(r"^[A-Za-z0-9]{8,12}$")
CHESS_COM_GAME_PATH = re.compile(r"^/(?:analysis/)?game/(?:live|daily|computer)/(\d+)")


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


def _source_details(
    site: str | None,
    link: str | None,
) -> tuple[GameSource, str | None, str | None]:
    """Identify supported PGN sources and their platform game IDs."""
    if site:
        parsed_site = urlparse(site)
        if parsed_site.hostname in {"lichess.org", "www.lichess.org"}:
            path_part = parsed_site.path.strip("/").split("/", 1)[0]
            game_id = path_part[:8] if LICHESS_GAME_ID.fullmatch(path_part) else None
            return "lichess", site, game_id

    if link:
        parsed_link = urlparse(link)
        if parsed_link.hostname in {"chess.com", "www.chess.com"}:
            game_match = CHESS_COM_GAME_PATH.match(parsed_link.path)
            game_id = game_match.group(1) if game_match else None
            return "chess_com", link, game_id

    if site and site.casefold() == "chess.com":
        return "chess_com", link, None

    return "other", link or site, None


def game_to_record(
    game: chess.pgn.Game,
    opening_catalog: OpeningCatalog | None = None,
) -> GameRecord:
    """Convert a parsed python-chess game into clean Chess Lab metadata."""
    ply_count = sum(1 for _ in game.mainline_moves())
    white = _clean_header(game, "White")
    black = _clean_header(game, "Black")
    site = _clean_header(game, "Site")
    link = _clean_header(game, "Link")
    source, source_url, source_game_id = _source_details(site, link)
    exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
    pgn = game.accept(exporter).strip() + "\n"
    fingerprint = sha256(pgn.encode("utf-8")).hexdigest()
    eco = _clean_header(game, "ECO")
    opening = _clean_header(game, "Opening")
    opening_ply: int | None = None
    if opening_catalog is not None and (eco is None or opening is None):
        opening_match = opening_catalog.classify_game(game)
        if opening_match is not None:
            eco = eco or opening_match.eco
            opening = opening or opening_match.name
            opening_ply = opening_match.ply

    return GameRecord(
        date=_clean_header(game, "Date"),
        white=white,
        black=black,
        white_elo=_parse_elo(_clean_header(game, "WhiteElo")),
        black_elo=_parse_elo(_clean_header(game, "BlackElo")),
        result=_clean_header(game, "Result"),
        time_control=_clean_header(game, "TimeControl"),
        eco=eco,
        opening=opening,
        opening_ply=opening_ply,
        move_count=(ply_count + 1) // 2,
        site=site,
        source=source,
        source_url=source_url,
        source_game_id=source_game_id,
        pgn=pgn,
        fingerprint=fingerprint,
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
        return list(iter_game_records(pgn_file))


def iter_game_records(
    pgn_file: TextIO,
    opening_catalog: OpeningCatalog | None = None,
) -> Iterator[GameRecord]:
    """Yield structured records without loading an entire PGN archive into memory."""
    while True:
        game = chess.pgn.read_game(pgn_file)
        if game is None:
            return
        yield game_to_record(game, opening_catalog)


def load_game_records(path: Path) -> list[GameRecord]:
    """Load every game in a PGN file as structured Chess Lab records."""
    return [game_to_record(game) for game in load_games(path)]
