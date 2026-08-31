"""Bounded public Lichess exports, partitioned by creation-time windows."""

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


BATCH_SIZE = 200
MAX_BYTES = 12 * 1024 * 1024
PERFS = {'rapid': 'rapid', 'blitz': 'blitz', 'bullet': 'bullet', 'ultraBullet': 'ultraBullet',
         'classical': 'classical', 'correspondence': 'correspondence',
         'all': 'ultraBullet,bullet,blitz,rapid,classical,correspondence'}
_request_lock = Lock()
_retry_after = 0.0


class LichessError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def export_games(username: str, since: int, until: int, time_class: str, *, limit: int = BATCH_SIZE + 1) -> list[dict]:
    """No credentials, redirects, arbitrary URLs, or unbounded game streams."""
    global _retry_after
    username = validate_chess_username('lichess', username).lower()
    if not _request_lock.acquire(blocking=False):
        raise LichessError('Another Lichess request is running. Wait a moment and retry.', 429)
    try:
        started = monotonic()
        if started < _retry_after:
            raise LichessError('Lichess is limiting requests. Wait at least a minute, then retry.', 429)
        # Provider-side perf filters use the search index, whose timestamp precision
        # and freshness differ. Export directly, then filter perf/variant locally.
        params = {'since': since, 'until': until, 'max': limit,
                  'sort': 'dateAsc', 'pgnInJson': 'true', 'moves': 'true', 'tags': 'true',
                  'opening': 'true', 'ongoing': 'false', 'finished': 'true'}
        with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False,
                          headers={'Accept': 'application/x-ndjson',
                                   'User-Agent': 'ChessLab/0.1 (+https://github.com/kileader/chess-lab)'}) as client:
            with client.stream('GET', f'https://lichess.org/api/games/user/{username}', params=params) as response:
                if response.status_code == 404:
                    raise LichessError('Lichess could not find that username. Check your saved username.', 404)
                if response.status_code == 429:
                    _retry_after = monotonic() + 60
                    raise LichessError('Lichess is limiting requests. Wait at least a minute, then retry.', 429)
                if response.status_code != 200:
                    raise LichessError('Lichess is unavailable or blocked this request. Try again later; PGN upload still works.')
                content = bytearray()
                # Check the deadline on small keep-alive chunks as well as game data.
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_BYTES:
                        raise LichessError('This Lichess batch is too large. Try a smaller date range or PGN upload.', 413)
                    if monotonic() - started > 40:
                        raise LichessError('Lichess took too long to respond. Retry the sync.', 504)
        games = [json.loads(line) for line in content.splitlines() if line.strip()]
        if len(games) > limit or any(not isinstance(game, dict) for game in games):
            raise ValueError('Invalid stream')
        for game in games:
            created = game.get('createdAt')
            if type(created) is not int or not since <= created < until:
                raise ValueError('Invalid creation date')
        return games
    except httpx.TimeoutException as error:
        raise LichessError('Lichess took too long to respond. Retry the sync.', 504) from error
    except httpx.HTTPError as error:
        raise LichessError('Could not reach Lichess. Try again later.') from error
    except (ValueError, UnicodeError) as error:
        raise LichessError('Lichess returned an unreadable export. No games from this batch were saved.') from error
    finally:
        _request_lock.release()


def date_bounds(date_from: date, date_to: date) -> tuple[int, int]:
    since = int(datetime.combine(date_from, time.min, timezone.utc).timestamp() * 1000)
    until = int(datetime.combine(date_to + timedelta(days=1), time.min, timezone.utc).timestamp() * 1000)
    return since, until


def month_bounds(month: str, date_from: date, date_to: date) -> tuple[int, int]:
    start = date.fromisoformat(month + '-01')
    following = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return date_bounds(max(start, date_from), min(following - timedelta(days=1), date_to))


def archive_months(username: str, date_from: date, date_to: date, time_class: str) -> list[str]:
    games = export_games(username, *date_bounds(date_from, date_to), time_class, limit=1)
    if not games:
        return []
    first = datetime.fromtimestamp(games[0]['createdAt'] / 1000, timezone.utc).date().replace(day=1)
    month = date_to.replace(day=1)
    months = []
    while month >= first:
        months.append(month.strftime('%Y-%m'))
        month = (month - timedelta(days=1)).replace(day=1)
    return months


def batch_records(username: str, since: int, until: int, time_class: str, catalog):
    games = export_games(username, since, until, time_class)
    if len(games) > BATCH_SIZE:
        # Split BEFORE saving. Lichess uses [since, until); no gaps or tied-date loss.
        if until - since <= 1:
            raise LichessError('Too many games share one timestamp. Please use PGN upload for this range.', 413)
        middle = (since + until) // 2
        return [], 0, [{'since': since, 'until': middle}, {'since': middle, 'until': until}]
    records, filtered = [], 0
    try:
        for entry in games:
            if (entry.get('variant') != 'standard' or entry.get('status') in {'created', 'started', 'aborted', 'noStart'}
                    or entry.get('perf') not in PERFS[time_class].split(',')):
                filtered += 1
                continue
            game_id, pgn = entry.get('id'), entry.get('pgn')
            if not isinstance(game_id, str) or not re.fullmatch(r'[A-Za-z0-9]{8}', game_id):
                raise ValueError('Invalid game ID')
            if not isinstance(pgn, str) or not pgn.strip() or len(pgn) > 128 * 1024:
                raise ValueError('Invalid PGN')
            stream = StringIO(pgn)
            game = chess.pgn.read_game(stream)
            if (game is None or game.errors or game.headers.get('Result') not in {'1-0', '0-1', '1/2-1/2'}
                    or game.headers.get('Variant', 'Standard') not in {'Standard', 'Chess'}
                    or chess.pgn.read_game(stream) is not None):
                raise ValueError('Invalid or unfinished game')
            record = game_to_record(game, catalog)
            if username.lower() not in {(record.white or '').lower(), (record.black or '').lower()}:
                raise ValueError('Wrong player')
            records.append(replace(record, source='lichess', source_game_id=game_id, source_url=f'https://lichess.org/{game_id}'))
    except (ValueError, TypeError, KeyError) as error:
        raise LichessError('Lichess returned an invalid game. No games from this batch were saved; try PGN upload instead.') from error
    return records, filtered, []
