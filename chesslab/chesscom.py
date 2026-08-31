"""Bounded, read-only Chess.com archive imports. No account credentials needed."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO
import json
import re
from threading import Lock
from time import monotonic

import chess.pgn
import httpx

from chesslab.identities import validate_chess_username
from chesslab.importer import game_to_record
from chesslab.openings import OpeningCatalog


API_ROOT = 'https://api.chess.com/pub/player'
MAX_BYTES = 20 * 1024 * 1024
MAX_MONTH_GAMES = 5000
REQUEST_SECONDS = 30
# The deployed API has one worker. Do not parallelize requests to Chess.com's API.
_request_lock = Lock()


class ChessComError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def fetch_json(path: str) -> dict:
    """Fetch only constructed Chess.com paths, with time and decoded-size bounds."""
    if not _request_lock.acquire(blocking=False):
        raise ChessComError('Another Chess.com request is running. Wait a moment and retry.', 429)
    try:
        started = monotonic()
        with httpx.Client(timeout=httpx.Timeout(10, connect=5), follow_redirects=False,
                          headers={'User-Agent': 'ChessLab/0.1 (+https://github.com/kileader/chess-lab)',
                                   'Accept': 'application/json'}) as client:
            with client.stream('GET', f'{API_ROOT}/{path}') as response:
                if response.status_code in {404, 410}:
                    raise ChessComError('Chess.com could not find that username or archive. Check your saved username.', 404)
                if response.status_code == 429:
                    raise ChessComError('Chess.com is limiting requests. Wait a minute, then retry.', 429)
                if response.status_code != 200:
                    raise ChessComError('Chess.com is unavailable or blocked this request. Try again later; PGN upload still works.')
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    content.extend(chunk)
                    if len(content) > MAX_BYTES:
                        raise ChessComError('This monthly archive is too large to sync. Please use smaller PGN uploads.', 413)
                    if monotonic() - started > REQUEST_SECONDS:
                        raise ChessComError('Chess.com took too long to respond. Retry this sync.', 504)
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError('Expected an object')
        return payload
    except httpx.TimeoutException as error:
        raise ChessComError('Chess.com took too long to respond. Retry this sync.', 504) from error
    except httpx.HTTPError as error:
        raise ChessComError('Could not reach Chess.com. Try again later.') from error
    except (ValueError, UnicodeError) as error:
        raise ChessComError('Chess.com returned an unreadable archive. No games from this month were saved.') from error
    finally:
        _request_lock.release()


def archive_months(username: str, date_from: date, date_to: date) -> list[str]:
    username = validate_chess_username('chess_com', username).lower()
    payload = fetch_json(f'{username}/games/archives')
    archives = payload.get('archives')
    if not isinstance(archives, list) or len(archives) > 1200:
        raise ChessComError('Chess.com returned an invalid archive list.')
    months = set()
    pattern = re.compile(rf'{re.escape(API_ROOT)}/{re.escape(username)}/games/(\d{{4}})/(0[1-9]|1[0-2])', re.IGNORECASE)
    for archive in archives:
        # Never fetch URLs supplied by the provider. Extract only valid months.
        match = pattern.fullmatch(archive) if isinstance(archive, str) else None
        if not match:
            raise ChessComError('Chess.com returned an invalid archive address.')
        month = f'{match[1]}-{match[2]}'
        if date_from.strftime('%Y-%m') <= month <= date_to.strftime('%Y-%m'):
            months.add(month)
    return sorted(months, reverse=True)


def monthly_records(username: str, month: str, date_from: date, date_to: date,
                    time_class: str, catalog: OpeningCatalog):
    """Parse one complete month before writing; filter by UTC game-end date."""
    username = validate_chess_username('chess_com', username).lower()
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        raise ValueError('Invalid month')
    payload = fetch_json(f'{username}/games/{month.replace("-", "/")}')
    games = payload.get('games')
    if not isinstance(games, list):
        raise ChessComError('Chess.com returned an invalid monthly archive.')
    if len(games) > MAX_MONTH_GAMES:
        raise ChessComError('This month has more than 5,000 games. Please use smaller PGN uploads.', 413)
    start = datetime.combine(date_from, time.min, timezone.utc).timestamp()
    end = datetime.combine(date_to + timedelta(days=1), time.min, timezone.utc).timestamp()
    records = []
    filtered = 0
    started = monotonic()
    try:
        for entry in games:
            if monotonic() - started > REQUEST_SECONDS:
                raise ChessComError('This month took too long to process. Please use smaller PGN uploads.', 413)
            if not isinstance(entry, dict):
                raise ValueError('Invalid game')
            ended = entry.get('end_time')
            if type(ended) is not int:
                raise ValueError('Missing end time')
            if (not start <= ended < end or entry.get('rules') != 'chess'
                    or (time_class != 'all' and entry.get('time_class') != time_class)):
                filtered += 1
                continue
            pgn = entry.get('pgn')
            if not isinstance(pgn, str) or not pgn.strip() or len(pgn) > 128 * 1024:
                raise ValueError('Invalid PGN')
            stream = StringIO(pgn)
            game = chess.pgn.read_game(stream)
            if (game is None or game.errors or game.headers.get('Result') not in {'1-0', '0-1', '1/2-1/2'}
                    or game.headers.get('Variant', 'Standard') not in {'Standard', 'Chess'}
                    or chess.pgn.read_game(stream) is not None):
                raise ValueError('Invalid or unfinished game')
            record = game_to_record(game, catalog)
            if username not in {(record.white or '').lower(), (record.black or '').lower()}:
                raise ValueError('Wrong player in PGN')
            url = entry.get('url')
            match = re.fullmatch(r'https://(?:www\.)?chess\.com/(?:game/(?:live|daily)|live/game)/(\d+)', url) if isinstance(url, str) else None
            if not match:
                raise ValueError('Invalid game URL')
            # Keep the original PGN fingerprint so previous uploads still deduplicate.
            records.append(replace(record, source='chess_com', source_url=url, source_game_id=match[1]))
    except (ValueError, TypeError, KeyError) as error:
        raise ChessComError('Chess.com returned an invalid game. No games from this month were saved; try PGN upload instead.') from error
    return records, filtered
