"""Copy one local library into an already signed-in hosted account, without deleting it."""
import argparse
import os
from pathlib import Path
import sqlite3
from uuid import UUID

from chesslab.postgres import PostgresGameStorage
from chesslab.storage import GAME_COLUMNS


def copy_library(source_path, local_user_id, target=None, subject=None):
    with sqlite3.connect(Path(source_path).resolve().as_uri() + '?mode=ro', uri=True) as source:
        source.row_factory = sqlite3.Row
        profile = source.execute('SELECT display_name FROM users WHERE id = ?', (local_user_id,)).fetchone()
        if not profile:
            raise ValueError('Local user not found.')
        identities = source.execute('SELECT platform, username, username_normalized FROM player_identities WHERE user_id = ?', (local_user_id,)).fetchall()
        games = source.execute('SELECT game.*, link.player_color FROM games game JOIN user_games link ON link.game_id = game.id WHERE link.user_id = ?', (local_user_id,)).fetchall()
        plans = source.execute('SELECT context, opening, status, note FROM repertoire_items WHERE user_id = ?', (local_user_id,)).fetchall()
        positions = source.execute('SELECT * FROM practice_positions WHERE user_id = ?', (local_user_id,)).fetchall()
    counts = {'games': len(games), 'repertoire_items': len(plans), 'practice_positions': len(positions)}
    if target is None:
        return counts
    # No auto-claiming: the destination must already exist after a real login.
    user_id = target.get_account_user(subject)
    if user_id is None:
        raise ValueError('Destination account not found. Sign in first and verify the Supabase user ID.')
    with target._connect() as connection:
        for identity in identities:
            existing = connection.execute('SELECT username_normalized FROM account_player_identities WHERE user_id = ? AND platform = ?', (user_id, identity['platform'])).fetchone()
            if existing and existing['username_normalized'] != identity['username_normalized']:
                raise ValueError('Destination chess identity differs. No data was copied.')
            connection.execute('INSERT INTO account_player_identities(user_id, platform, username, username_normalized) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING', (user_id, identity['platform'], identity['username'], identity['username_normalized']))
        connection.execute("UPDATE users SET display_name = ? WHERE id = ? AND display_name = 'Chess player'", (profile['display_name'], user_id))
        columns = ', '.join(GAME_COLUMNS)
        placeholders = ', '.join('?' for _ in GAME_COLUMNS)
        for game in games:
            values = tuple(game[column] for column in GAME_COLUMNS)
            inserted = connection.execute(f'INSERT INTO games ({columns}, owner_user_id) VALUES ({placeholders}, ?) ON CONFLICT DO NOTHING RETURNING id', (*values, user_id)).fetchone()
            if inserted is None:
                inserted = connection.execute('SELECT id FROM games WHERE owner_user_id = ? AND (fingerprint = ? OR (source = ? AND source_game_id = ?))', (user_id, game['fingerprint'], game['source'], game['source_game_id'])).fetchone()
            connection.execute('INSERT INTO user_games(user_id, game_id, player_color) VALUES (?, ?, ?) ON CONFLICT DO NOTHING', (user_id, inserted['id'], game['player_color']))
        for plan in plans:
            connection.execute('INSERT INTO repertoire_items(user_id, context, opening, status, note) VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING', (user_id, *tuple(plan)))
        fields = ('position_key', 'fen', 'family', 'player_color', 'line', 'san_path', 'date_from', 'date_to', 'note', 'candidate_move', 'examples', 'created_at')
        for position in positions:
            connection.execute(f"INSERT INTO practice_positions(user_id, {', '.join(fields)}) VALUES (?, {', '.join('?' for _ in fields)}) ON CONFLICT DO NOTHING", (user_id, *(position[field] for field in fields)))
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--local-user-id', type=int, required=True)
    parser.add_argument('--auth-subject', type=UUID)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    target = None
    if args.apply:
        if not args.auth_subject or not os.getenv('DATABASE_URL'):
            parser.error('--apply requires --auth-subject and DATABASE_URL.')
        target = PostgresGameStorage(os.environ['DATABASE_URL'])
    counts = copy_library(args.source, args.local_user_id, target, str(args.auth_subject) if args.auth_subject else None)
    print(('Copied (existing entries preserved): ' if args.apply else 'Dry run; nothing changed: ') + str(counts))
