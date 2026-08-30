"""The explorer counts positions and results, not final opening labels."""

import pytest

from chesslab.explorer import explore_position


def record(moves, result="1-0", **extra):
    return {"pgn": f"{moves} {result}", "result": result,
            "date": "2026.08.30", "source_url": "https://lichess.org/example", **extra}


def test_replies_count_transpositions_and_player_relative_results():
    records = [
        record("1. Nf3 d5 2. d4 Nf6 3. c4"),
        record("1. d4 Nf6 2. Nf3 d5 3. c4", "0-1"),
        record("1. d4 d5 2. Nf3 Nf6 3. e3", "1/2-1/2"),
    ]
    result = explore_position(records, ["d4", "d5", "Nf3", "Nf6"], [], "white")
    assert result["games"] == 3
    assert result["score"] == .5
    c4, e3 = result["moves"]
    assert (c4["san"], c4["games"], c4["wins"], c4["losses"]) == ("c4", 2, 1, 1)
    assert c4["frequency"] == pytest.approx(2 / 3)
    assert e3["draws"] == 1
    assert result["turn"] == "white"


def test_black_score_unfinished_and_ended_games():
    result = explore_position([
        record("1. e4 e5", "0-1"), record("1. e4 c5", "*"),
        record("1. e4", "1/2-1/2"),
    ], ["e4"], [], "black")
    assert result["score"] == .75
    assert result["unfinished"] == 1
    assert result["ended_games"] == 1
    branches = {row["san"]: row for row in result["moves"]}
    assert branches["e5"]["score"] == 1
    assert branches["c5"]["score"] is None
    assert branches["c5"]["score_change"] is None


def test_position_counted_only_once_per_game():
    result = explore_position([record("1. Nf3 Nf6 2. Ng1 Ng8 3. e4")], [], [], "white")
    assert result["games"] == 1
    assert [row["san"] for row in result["moves"]] == ["Nf3"]


def test_continuation_changes_board_and_next_turn():
    result = explore_position([record("1. e4 e5 2. Nf3")], ["e4"], ["e7e5"], "white")
    assert result["san_path"] == ["e4", "e5"]
    assert result["turn"] == "white"
    assert result["moves"][0]["uci"] == "g1f3"


@pytest.mark.parametrize("line", [["a1a8"], ["0000"], ["bad"], ["e2e4"] * 25])
def test_invalid_continuations_are_rejected(line):
    with pytest.raises(ValueError):
        explore_position([], ["e4"], line, "white")


def test_empty_and_malformed_records():
    result = explore_position([record("1. e4 e5 2. Ke4")], ["e4"], [], "white")
    assert result["games"] == 0
    assert result["score"] is None
    assert result["moves"] == []
    assert result["skipped_games"] == 1
