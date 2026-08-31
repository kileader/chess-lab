"""Validation shared by account setup and identity edits."""

import re


def validate_chess_username(platform: str, username: str) -> str:
    username = username.strip()
    if platform == 'other':
        if not 1 <= len(username) <= 80 or not username.isprintable():
            raise ValueError('Enter a PGN player name of 1–80 printable characters.')
    elif platform in {'lichess', 'chess_com'}:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', username):
            raise ValueError('Chess usernames must be 1–40 letters, numbers, underscores, or hyphens.')
    else:
        raise ValueError('Choose Lichess, Chess.com, or Other.')
    return username
