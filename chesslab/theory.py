"""Small, local Stockfish helpers for objective opening assessments."""

import os
from io import StringIO
from pathlib import Path

import chess.engine
import chess.pgn


DEFAULT_ENGINE_PATH = Path("tools/stockfish/sf18/stockfish/stockfish-windows-x86-64.exe")


def assess_pgn_opening(
    pgn_text: str,
    opening_ply: int | None,
    player_color: str,
) -> dict[str, object] | None:
    """Evaluate the classified opening position from the player's perspective."""
    engine_path = Path(os.environ.get("CHESSLAB_STOCKFISH_PATH", DEFAULT_ENGINE_PATH))
    if not engine_path.is_file():
        return None
    game = chess.pgn.read_game(StringIO(pgn_text))
    if game is None:
        return None
    board = game.board()
    for move in list(game.mainline_moves())[:opening_ply or 12]:
        board.push(move)
    with chess.engine.SimpleEngine.popen_uci(str(engine_path)) as engine:
        info = engine.analyse(board, chess.engine.Limit(depth=14))
    white_centipawns = info["score"].white().score(mate_score=100_000)
    if white_centipawns is None:
        return None
    player_centipawns = white_centipawns if player_color == "white" else -white_centipawns
    if player_centipawns >= 50:
        verdict = "this line looks good for you"
    elif player_centipawns <= -50:
        verdict = "your opponent has an edge in this line"
    else:
        verdict = "this line looks about even"
    return {
        "opening_ply": opening_ply or 12,
        "white_centipawns": white_centipawns,
        "player_centipawns": player_centipawns,
        "verdict": verdict,
    }


def first_major_mistake(pgn_text: str, player_color: str) -> dict[str, object] | None:
    """Find the first player move that drops the evaluation by a full pawn."""
    engine_path = Path(os.environ.get("CHESSLAB_STOCKFISH_PATH", DEFAULT_ENGINE_PATH))
    if not engine_path.is_file():
        return None
    game = chess.pgn.read_game(StringIO(pgn_text))
    if game is None:
        return None
    board = game.board()
    player_turn = chess.WHITE if player_color == "white" else chess.BLACK
    with chess.engine.SimpleEngine.popen_uci(str(engine_path)) as engine:
        for ply, move in enumerate(game.mainline_moves(), start=1):
            if board.turn != player_turn:
                board.push(move)
                continue
            before = engine.analyse(board, chess.engine.Limit(depth=8))["score"].pov(player_turn).score(mate_score=100_000)
            san = board.san(move)
            board.push(move)
            after = engine.analyse(board, chess.engine.Limit(depth=8))["score"].pov(player_turn).score(mate_score=100_000)
            if before is not None and after is not None and before - after >= 100:
                return {"move": san, "move_number": (ply + 1) // 2, "centipawns_lost": before - after}
    return None
