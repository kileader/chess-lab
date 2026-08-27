"""Structured data models used by Chess Lab."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameRecord:
    """Clean metadata extracted from one parsed chess game."""

    date: str | None
    white: str | None
    black: str | None
    white_elo: int | None
    black_elo: int | None
    result: str | None
    time_control: str | None
    eco: str | None
    opening: str | None
    move_count: int
