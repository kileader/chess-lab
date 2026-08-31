"""Explicitly published projections; private libraries are never public queries."""

import io
import json
from datetime import datetime, timezone
from uuid import uuid4

import chess.pgn


SOCIAL_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS community_profiles (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        public_id TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        bio TEXT NOT NULL DEFAULT '',
        visible INTEGER NOT NULL DEFAULT 0 CHECK(visible IN (0, 1))
    )""",
    """CREATE TABLE IF NOT EXISTS community_games (
        public_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES community_profiles(user_id) ON DELETE CASCADE,
        game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
        caption TEXT NOT NULL DEFAULT '',
        snapshot TEXT NOT NULL,
        shared_at TEXT NOT NULL,
        UNIQUE(user_id, game_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_community_games_recent ON community_games(shared_at, public_id)",
)


def game_snapshot(row):
    """Allowlist metadata and mainline moves. Never expose raw PGN or annotations."""
    if len(row['pgn'].encode('utf-8')) > 128 * 1024:
        raise ValueError('This PGN is too large to share. Your private game is unchanged.')
    game = chess.pgn.read_game(io.StringIO(row['pgn']))
    if game is None or game.errors or game.headers.get('Variant', 'Standard') not in {'Standard', 'Chess'}:
        raise ValueError('Only valid standard-chess games can be shared.')
    board = game.board()
    positions, moves = [board.fen()], []
    for move in game.mainline_moves():
        if len(moves) >= 1000:
            raise ValueError('This game has too many moves to share.')
        prefix = f'{board.fullmove_number}.' if board.turn else f'{board.fullmove_number}...'
        moves.append(f'{prefix} {board.san(move)}')
        board.push(move)
        positions.append(board.fen())
    # Imported strings are untrusted. Render as text, and bound public payloads.
    text_fields = ('white', 'black', 'date', 'result', 'opening', 'time_control', 'source')
    snapshot = {key: str(row[key])[:160] if row[key] is not None else None for key in text_fields}
    snapshot.update({key: row[key] for key in ('white_elo', 'black_elo')})
    return {**snapshot, 'moves': moves, 'positions': positions}


class CommunityStorage:
    def __init__(self, storage):
        self.storage = storage

    def settings(self, user_id):
        with self.storage._connect() as connection:
            row = connection.execute(
                'SELECT public_id, name, bio, visible FROM community_profiles WHERE user_id = ?', (user_id,)
            ).fetchone()
        return {**dict(row), 'visible': bool(row['visible'])} if row else {
            'public_id': None, 'name': '', 'bio': '', 'visible': False,
        }

    def save_profile(self, user_id, name, bio, visible):
        with self.storage._connect() as connection:
            self.storage._lock_account(connection, user_id)
            connection.execute(
                '''INSERT INTO community_profiles(user_id, public_id, name, bio, visible)
                   VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE
                   SET name = excluded.name, bio = excluded.bio, visible = excluded.visible''',
                (user_id, str(uuid4()), name, bio, int(visible)),
            )
            if not visible:
                # Re-enabling a profile must not silently republish old shares.
                connection.execute('DELETE FROM community_games WHERE user_id = ?', (user_id,))
        return self.settings(user_id)

    def library(self, user_id, limit, offset):
        with self.storage._connect() as connection:
            total = connection.execute('SELECT COUNT(*) AS n FROM games WHERE owner_user_id = ?', (user_id,)).fetchone()['n']
            rows = connection.execute(
                '''SELECT g.id, g.white, g.black, g.date, g.result, g.opening,
                          s.public_id AS share_id, s.caption
                   FROM games g LEFT JOIN community_games s ON s.game_id = g.id AND s.user_id = ?
                   WHERE g.owner_user_id = ? ORDER BY g.id DESC LIMIT ? OFFSET ?''',
                (user_id, user_id, limit, offset),
            ).fetchall()
        return {'total': total, 'games': [dict(row) for row in rows]}

    def share(self, user_id, game_id, caption):
        with self.storage._connect() as connection:
            self.storage._lock_account(connection, user_id)
            row = connection.execute('SELECT * FROM games WHERE id = ? AND owner_user_id = ?', (game_id, user_id)).fetchone()
            if row is None:
                return None
            profile = connection.execute('SELECT visible FROM community_profiles WHERE user_id = ?', (user_id,)).fetchone()
            if profile is None or not profile['visible']:
                raise ValueError('Publish your community profile before sharing a game.')
            existing = connection.execute('SELECT public_id FROM community_games WHERE user_id = ? AND game_id = ?', (user_id, game_id)).fetchone()
            count = connection.execute('SELECT COUNT(*) AS n FROM community_games WHERE user_id = ?', (user_id,)).fetchone()['n']
            if existing is None and count >= 100:
                raise ValueError('You can share up to 100 games. Unshare one before adding another.')
            snapshot = json.dumps(game_snapshot(row), ensure_ascii=False)
            public_id = existing['public_id'] if existing else str(uuid4())
            connection.execute(
                '''INSERT INTO community_games(public_id, user_id, game_id, caption, snapshot, shared_at)
                   VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(user_id, game_id) DO UPDATE
                   SET caption = excluded.caption, snapshot = excluded.snapshot''',
                (public_id, user_id, game_id, caption, snapshot, datetime.now(timezone.utc).isoformat()),
            )
        return {'public_id': public_id}

    def unshare(self, user_id, game_id):
        with self.storage._connect() as connection:
            self.storage._lock_account(connection, user_id)
            if connection.execute('SELECT id FROM games WHERE id = ? AND owner_user_id = ?', (game_id, user_id)).fetchone() is None:
                return False
            connection.execute('DELETE FROM community_games WHERE user_id = ? AND game_id = ?', (user_id, game_id))
        return True

    @staticmethod
    def _published(row, detail=False):
        snapshot = json.loads(row['snapshot'])
        if not detail:
            snapshot.pop('moves')
            snapshot.pop('positions')
        return {**snapshot, 'public_id': row['public_id'], 'caption': row['caption'],
                'shared_at': row['shared_at'], 'profile_id': row['profile_id'], 'name': row['name']}

    def public_games(self, limit=20, offset=0, profile_id=None, share_id=None):
        where, params = ['p.visible = 1', 'g.owner_user_id = s.user_id'], []
        if profile_id is not None:
            where.append('p.public_id = ?')
            params.append(profile_id)
        if share_id is not None:
            where.append('s.public_id = ?')
            params.append(share_id)
        with self.storage._connect() as connection:
            rows = connection.execute(
                '''SELECT s.public_id, s.caption, s.snapshot, s.shared_at, p.public_id AS profile_id, p.name
                   FROM community_games s JOIN community_profiles p ON p.user_id = s.user_id
                   JOIN games g ON g.id = s.game_id WHERE ''' + ' AND '.join(where) +
                ' ORDER BY s.shared_at DESC, s.public_id DESC LIMIT ? OFFSET ?', (*params, limit, offset),
            ).fetchall()
        return [self._published(row, detail=share_id is not None) for row in rows]

    def profiles(self, limit=20, offset=0, profile_id=None):
        where, params = 'p.visible = 1', []
        if profile_id is not None:
            where += ' AND p.public_id = ?'
            params.append(profile_id)
        with self.storage._connect() as connection:
            rows = connection.execute(
                '''SELECT p.public_id, p.name, p.bio,
                   (SELECT COUNT(*) FROM community_games s JOIN games g ON g.id = s.game_id
                    WHERE s.user_id = p.user_id AND g.owner_user_id = s.user_id) AS shared_games
                   FROM community_profiles p WHERE ''' + where +
                ' ORDER BY LOWER(p.name), p.public_id LIMIT ? OFFSET ?', (*params, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]
