"""Position-based next-move frequencies and player-relative game results."""

from functools import lru_cache
from io import StringIO
from collections.abc import Iterable

import chess
import chess.pgn


MAX_GAME_PLIES = 80
MAX_CONTINUATION_PLIES = 24


@lru_cache(maxsize=8192)
def _positions(pgn: str) -> dict[str, tuple[str, str] | None] | None:
    """Index the first visit to each position; cache depends on PGN content only."""
    game = chess.pgn.read_game(StringIO(pgn))
    if game is None or game.errors:
        return None
    board = game.board()
    positions: dict[str, tuple[str, str] | None] = {}
    for ply, move in enumerate(game.mainline_moves()):
        if ply >= MAX_GAME_PLIES:
            break
        positions.setdefault(board.epd(), (move.uci(), board.san(move)))
        board.push(move)
    else:
        positions.setdefault(board.epd(), None)
    return positions


def _empty_results() -> dict[str, int]:
    return {"games": 0, "wins": 0, "draws": 0, "losses": 0, "unfinished": 0}


def _add_result(totals: dict, result: str | None, color: str) -> None:
    totals["games"] += 1
    if result == "1/2-1/2":
        totals["draws"] += 1
    elif result in {"1-0", "0-1"}:
        won = result == ("1-0" if color == "white" else "0-1")
        totals["wins" if won else "losses"] += 1
    else:
        totals["unfinished"] += 1


def _score(totals: dict) -> float | None:
    completed = totals["wins"] + totals["draws"] + totals["losses"]
    return (totals["wins"] + totals["draws"] / 2) / completed if completed else None


def explore_position(
    records: Iterable[dict], root_moves: list[str], continuation: list[str], color: str,
) -> dict:
    """Count games reaching a position, regardless of final opening label or move order.

    Only the first visit per game counts. Results describe the full game, not
    position evaluation. Unfinished games contribute frequency but not score.
    """
    if len(continuation) > MAX_CONTINUATION_PLIES:
        raise ValueError("Explore at most 24 half-moves beyond the opening start.")
    board = chess.Board()
    san_path: list[str] = []
    for san in root_moves:
        move = board.parse_san(san)
        san_path.append(board.san(move))
        board.push(move)
    for uci in continuation:
        move = board.parse_uci(uci)
        if not move or move not in board.legal_moves:
            raise ValueError("A continuation must contain legal moves.")
        san_path.append(board.san(move))
        board.push(move)
    target = board.epd()
    totals = _empty_results()
    branches: dict[str, dict] = {}
    skipped = 0
    ended = 0
    for record in records:
        positions = _positions(record["pgn"])
        if positions is None:
            skipped += 1
            continue
        if target not in positions:
            continue
        _add_result(totals, record["result"], color)
        following = positions[target]
        if following is None:
            ended += 1
            continue
        uci, san = following
        branch = branches.setdefault(uci, {
            **_empty_results(), "uci": uci, "san": san, "examples": [],
        })
        _add_result(branch, record["result"], color)
        if len(branch["examples"]) < 3:
            branch["examples"].append({
                "date": record["date"], "source_url": record["source_url"],
                "result": record["result"],
            })
    parent_score = _score(totals)
    for branch in branches.values():
        branch["score"] = _score(branch)
        branch["frequency"] = branch["games"] / totals["games"]
        branch["score_change"] = (
            branch["score"] - parent_score
            if branch["score"] is not None and parent_score is not None else None
        )
    return {
        **totals, "score": parent_score, "fen": board.fen(), "san_path": san_path,
        "root_plies": len(root_moves), "player_color": color,
        "turn": "white" if board.turn else "black", "ended_games": ended,
        "skipped_games": skipped,
        "at_limit": len(continuation) >= MAX_CONTINUATION_PLIES,
        "moves": sorted(branches.values(), key=lambda row: (-row["games"], row["san"])),
    }
