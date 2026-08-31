"""SQLite persistence for structured Chess Lab game records."""

import io
import json
import math
import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path

import chess.pgn

from chesslab.models import GameRecord


CREATE_GAMES_TABLE = """
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    white TEXT,
    black TEXT,
    white_elo INTEGER,
    black_elo INTEGER,
    result TEXT,
    time_control TEXT,
    eco TEXT,
    opening TEXT,
    opening_ply INTEGER,
    move_count INTEGER NOT NULL,
    site TEXT,
    source TEXT NOT NULL DEFAULT 'other',
    source_url TEXT,
    source_game_id TEXT,
    pgn TEXT NOT NULL,
    fingerprint TEXT NOT NULL
)
"""

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_PLAYER_IDENTITIES_TABLE = """
CREATE TABLE IF NOT EXISTS player_identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    username TEXT NOT NULL,
    username_normalized TEXT NOT NULL,
    UNIQUE(platform, username_normalized)
)
"""

CREATE_USER_GAMES_TABLE = """
CREATE TABLE IF NOT EXISTS user_games (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_color TEXT NOT NULL CHECK(player_color IN ('white', 'black')),
    PRIMARY KEY (user_id, game_id)
)
"""

CREATE_REPERTOIRE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS repertoire_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    context TEXT NOT NULL,
    opening TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('keep', 'practice', 'try')),
    note TEXT NOT NULL DEFAULT '',
    UNIQUE(user_id, context, opening)
)
"""

CREATE_PRACTICE_POSITIONS_TABLE = """
CREATE TABLE IF NOT EXISTS practice_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    position_key TEXT NOT NULL,
    fen TEXT NOT NULL,
    family TEXT NOT NULL,
    player_color TEXT NOT NULL CHECK(player_color IN ('white', 'black')),
    line TEXT NOT NULL,
    san_path TEXT NOT NULL,
    date_from TEXT,
    date_to TEXT,
    note TEXT NOT NULL DEFAULT '',
    candidate_move TEXT NOT NULL DEFAULT '',
    examples TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, position_key, player_color)
)
"""

CREATE_ACCOUNTS_TABLE = """
CREATE TABLE IF NOT EXISTS accounts (
    subject TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE
)
"""

CREATE_ACCOUNT_IDENTITIES_TABLE = """
CREATE TABLE IF NOT EXISTS account_player_identities (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform TEXT NOT NULL CHECK(platform IN ('lichess', 'chess_com')),
    username TEXT NOT NULL,
    username_normalized TEXT NOT NULL,
    PRIMARY KEY (user_id, platform, username_normalized)
)
"""

OWNED_GAME_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS games_owned_source_identity ON games "
    "(COALESCE(owner_user_id, 0), source, source_game_id) WHERE source_game_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS games_owned_fingerprint ON games "
    "(COALESCE(owner_user_id, 0), fingerprint) WHERE fingerprint IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS games_owner ON games(owner_user_id, id)",
)

MIGRATION_COLUMNS = {
    "opening_ply": "INTEGER",
    "site": "TEXT",
    "source": "TEXT NOT NULL DEFAULT 'other'",
    "source_url": "TEXT",
    "source_game_id": "TEXT",
    "pgn": "TEXT",
    "fingerprint": "TEXT",
}

GAME_COLUMNS = (
    "date",
    "white",
    "black",
    "white_elo",
    "black_elo",
    "result",
    "time_control",
    "eco",
    "opening",
    "opening_ply",
    "move_count",
    "site",
    "source",
    "source_url",
    "source_game_id",
    "pgn",
    "fingerprint",
)


class SQLiteGameStorage:
    """Store and retrieve game records from a local SQLite database."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(CREATE_GAMES_TABLE)
        existing_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(games)")
        }
        for column, definition in MIGRATION_COLUMNS.items():
            if column not in existing_columns:
                connection.execute(
                    f"ALTER TABLE games ADD COLUMN {column} {definition}"
                )
        connection.execute(CREATE_USERS_TABLE)
        if "owner_user_id" not in existing_columns:
            connection.execute("ALTER TABLE games ADD COLUMN owner_user_id INTEGER REFERENCES users(id)")
        # Build replacement indexes before dropping the old global constraints.
        for statement in OWNED_GAME_INDEXES:
            connection.execute(statement)
        connection.execute("DROP INDEX IF EXISTS games_source_identity")
        connection.execute("DROP INDEX IF EXISTS games_fingerprint")
        connection.execute(CREATE_PLAYER_IDENTITIES_TABLE)
        connection.execute(CREATE_USER_GAMES_TABLE)
        connection.execute(CREATE_REPERTOIRE_ITEMS_TABLE)
        connection.execute(CREATE_PRACTICE_POSITIONS_TABLE)
        connection.execute(CREATE_ACCOUNTS_TABLE)
        connection.execute(CREATE_ACCOUNT_IDENTITIES_TABLE)
        identity_pk = [row['name'] for row in sorted(
            connection.execute('PRAGMA table_info(account_player_identities)'), key=lambda row: row['pk']) if row['pk']]
        if identity_pk == ['user_id', 'platform']:
            # SQLite cannot alter a primary key. Copy every identity atomically.
            if not connection.in_transaction:
                connection.execute('BEGIN IMMEDIATE')
            connection.execute(CREATE_ACCOUNT_IDENTITIES_TABLE.replace('account_player_identities', 'account_player_identities_v2'))
            connection.execute('INSERT INTO account_player_identities_v2 SELECT * FROM account_player_identities')
            connection.execute('DROP TABLE account_player_identities')
            connection.execute('ALTER TABLE account_player_identities_v2 RENAME TO account_player_identities')
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_repertoire_items_user_context "
            "ON repertoire_items(user_id, context)"
        )
        connection.execute("PRAGMA optimize")
        return connection

    @staticmethod
    def _link_games_to_identities(connection: sqlite3.Connection) -> None:
        """Associate games with matching platform identities without changing games."""
        connection.execute(
            """
            INSERT INTO user_games (user_id, game_id, player_color)
            SELECT
                identity.user_id,
                game.id,
                CASE
                    WHEN LOWER(game.white) = identity.username_normalized THEN 'white'
                    ELSE 'black'
                END
            FROM player_identities AS identity
            JOIN games AS game ON game.source = identity.platform
            WHERE game.owner_user_id IS NULL
              AND NOT EXISTS (SELECT 1 FROM accounts WHERE accounts.user_id = identity.user_id)
              AND (LOWER(game.white) = identity.username_normalized
               OR LOWER(game.black) = identity.username_normalized)
            ON CONFLICT DO NOTHING
            """
        )

    def save_games(self, games: Iterable[GameRecord]) -> int:
        """Insert all supplied games in one transaction and return the count."""
        _, games_added = self.import_games(games)
        return games_added

    def import_games(self, games: Iterable[GameRecord], *, owner_user_id: int | None = None) -> tuple[int, int]:
        """Stream games through one transaction and return received/added counts."""
        placeholders = ", ".join("?" for _ in GAME_COLUMNS)
        columns = ", ".join(GAME_COLUMNS)
        insert_query = f"INSERT INTO games ({columns}, owner_user_id) VALUES ({placeholders}, ?) ON CONFLICT DO NOTHING"
        games_received = 0
        games_added = 0

        with self._connect() as connection:
            if owner_user_id is not None:
                self._lock_account(connection, owner_user_id)
            for game in games:
                game_row = tuple(getattr(game, column) for column in GAME_COLUMNS)
                cursor = connection.execute(insert_query, (*game_row, owner_user_id))
                games_received += 1
                games_added += cursor.rowcount
            if owner_user_id is None:
                self._link_games_to_identities(connection)
            else:
                self._relink_owned_games(connection, owner_user_id)

        return games_received, games_added

    def get_or_create_user_for_identity(
        self,
        *,
        display_name: str,
        platform: str,
        username: str,
    ) -> int:
        """Return the user owning an identity, creating and linking it if needed."""
        normalized_username = username.strip().casefold()
        if not display_name.strip() or not normalized_username:
            raise ValueError("Display name and username are required.")

        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT user_id FROM player_identities
                WHERE platform = ? AND username_normalized = ?
                """,
                (platform, normalized_username),
            ).fetchone()
            if existing is not None:
                user_id = int(existing["user_id"])
            else:
                cursor = connection.execute(
                    "INSERT INTO users (display_name) VALUES (?) RETURNING id",
                    (display_name.strip(),),
                )
                user_id = int(cursor.fetchone()["id"])
                connection.execute(
                    """
                    INSERT INTO player_identities
                        (user_id, platform, username, username_normalized)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, platform, username.strip(), normalized_username),
                )
            self._link_games_to_identities(connection)

        return user_id

    def get_account_user(self, subject: str) -> int | None:
        with self._connect() as connection:
            row = connection.execute("SELECT user_id FROM accounts WHERE subject = ?", (subject,)).fetchone()
        return int(row["user_id"]) if row else None

    def ensure_account(self, subject: str) -> int:
        """Provision by verified auth subject, never by email or chess handle."""
        with self._connect() as connection:
            existing = connection.execute("SELECT user_id FROM accounts WHERE subject = ?", (subject,)).fetchone()
            if existing:
                return int(existing["user_id"])
            row = connection.execute("INSERT INTO users (display_name) VALUES (?) RETURNING id", ("Chess player",)).fetchone()
            user_id = int(row["id"])
            inserted = connection.execute("INSERT INTO accounts(subject, user_id) VALUES (?, ?) ON CONFLICT DO NOTHING", (subject, user_id))
            if inserted.rowcount == 0:
                connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
            result = connection.execute("SELECT user_id FROM accounts WHERE subject = ?", (subject,)).fetchone()
        return int(result["user_id"])

    def configure_account(self, user_id: int, display_name: str, platform: str, username: str) -> None:
        """Set an analysis identity; it grants access only to this account's imports."""
        with self._connect() as connection:
            self._lock_account(connection, user_id)
            existing = connection.execute("SELECT platform, username_normalized FROM account_player_identities WHERE user_id = ?", (user_id,)).fetchone()
            if existing and (existing["platform"] != platform or existing["username_normalized"] != username.casefold()):
                raise ValueError("Your profile is already set up. Use account settings to change your usernames.")
            connection.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, user_id))
            connection.execute("""INSERT INTO account_player_identities (user_id, platform, username, username_normalized)
                VALUES (?, ?, ?, ?) ON CONFLICT(user_id, platform, username_normalized) DO NOTHING""", (user_id, platform, username, username.casefold()))
            self._relink_owned_games(connection, user_id)

    @staticmethod
    def _lock_account(connection, user_id: int) -> None:
        # Serialize imports and identity edits for this account on both databases.
        connection.execute('UPDATE users SET display_name = display_name WHERE id = ?', (user_id,))

    @staticmethod
    def _relink_owned_games(connection, user_id: int) -> None:
        """Rebuild only this owner's links, excluding games matching both sides."""
        connection.execute('DELETE FROM user_games WHERE user_id = ? AND game_id IN '
                           '(SELECT id FROM games WHERE owner_user_id = ?)', (user_id, user_id))
        connection.execute("""
            INSERT INTO user_games(user_id, game_id, player_color)
            SELECT ?, game.id,
                CASE WHEN MAX(CASE WHEN LOWER(game.white) = identity.username_normalized THEN 1 ELSE 0 END) = 1
                     THEN 'white' ELSE 'black' END
            FROM games AS game
            JOIN account_player_identities AS identity
              ON identity.user_id = game.owner_user_id AND identity.platform = game.source
            WHERE game.owner_user_id = ?
            GROUP BY game.id
            HAVING MAX(CASE WHEN LOWER(game.white) = identity.username_normalized THEN 1 ELSE 0 END)
                <> MAX(CASE WHEN LOWER(game.black) = identity.username_normalized THEN 1 ELSE 0 END)
            ON CONFLICT(user_id, game_id) DO UPDATE SET player_color = excluded.player_color
        """, (user_id, user_id))

    def update_account_identities(self, user_id: int, identities: list[dict[str, str]]) -> dict[str, int]:
        """Replace an account's username list; keep games and study notes intact."""
        if not 1 <= len(identities) <= 10:
            raise ValueError('Save between 1 and 10 chess usernames.')
        normalized = []
        seen = set()
        for identity in identities:
            platform, username = identity['platform'], identity['username'].strip()
            if platform not in {'lichess', 'chess_com'} or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', username):
                raise ValueError('Choose a valid platform and chess username.')
            key = (platform, username.casefold())
            if key in seen:
                raise ValueError('Each username can appear only once per platform (ignoring capitalization).')
            seen.add(key)
            normalized.append((user_id, platform, username, username.casefold()))
        with self._connect() as connection:
            self._lock_account(connection, user_id)
            if not connection.execute('SELECT user_id FROM accounts WHERE user_id = ?', (user_id,)).fetchone():
                raise ValueError('Username settings require a signed-in account.')
            connection.execute('DELETE FROM account_player_identities WHERE user_id = ?', (user_id,))
            for identity in normalized:
                connection.execute('INSERT INTO account_player_identities '
                                   '(user_id, platform, username, username_normalized) VALUES (?, ?, ?, ?)', identity)
            self._relink_owned_games(connection, user_id)
            total = connection.execute('SELECT COUNT(*) AS total FROM games WHERE owner_user_id = ?', (user_id,)).fetchone()['total']
            matched = connection.execute('SELECT COUNT(*) AS total FROM user_games link JOIN games game ON game.id = link.game_id '
                                         'WHERE link.user_id = ? AND game.owner_user_id = ?', (user_id, user_id)).fetchone()['total']
        return {'library_games': int(total), 'matched_games': int(matched)}

    def get_user_profile(self, user_id: int) -> dict[str, object] | None:
        """Return one user and all linked platform identities."""
        with self._connect() as connection:
            user = connection.execute(
                "SELECT id, display_name FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if user is None:
                return None
            identities = connection.execute(
                """
                SELECT platform, username FROM player_identities WHERE user_id = ?
                UNION ALL
                SELECT platform, username FROM account_player_identities WHERE user_id = ?
                ORDER BY platform, username
                """,
                (user_id, user_id),
            ).fetchall()

        return {
            "id": int(user["id"]),
            "display_name": str(user["display_name"]),
            "identities": [dict(identity) for identity in identities],
        }

    def save_repertoire_items(
        self, user_id: int, items: Iterable[dict[str, str]]
    ) -> list[dict[str, object]] | None:
        """Create or update the selected user's opening plan."""
        if self.get_user_profile(user_id) is None:
            return None
        with self._connect() as connection:
            for item in items:
                connection.execute(
                    """
                    INSERT INTO repertoire_items (user_id, context, opening, status, note)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, context, opening) DO UPDATE SET
                        status = excluded.status,
                        note = excluded.note
                    """,
                    (
                        user_id,
                        item["context"].strip(),
                        item["opening"].strip(),
                        item["status"],
                        item.get("note", "").strip(),
                    ),
                )
        return self.get_user_repertoire(user_id)

    def get_user_repertoire(self, user_id: int) -> list[dict[str, object]] | None:
        """Return a user's saved opening plan, organized by playing context."""
        if self.get_user_profile(user_id) is None:
            return None
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, context, opening, status, note
                FROM repertoire_items
                WHERE user_id = ?
                ORDER BY
                    CASE context
                        WHEN 'As White' THEN 1
                        WHEN 'As Black vs 1.e4' THEN 2
                        WHEN 'As Black vs 1.d4' THEN 3
                        ELSE 4
                    END,
                    id
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_repertoire_item(
        self, user_id: int, item_id: int, item: dict[str, str]
    ) -> dict[str, object] | None:
        """Update one saved opening-plan entry owned by a user."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE repertoire_items
                SET context = ?, opening = ?, status = ?, note = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    item["context"].strip(),
                    item["opening"].strip(),
                    item["status"],
                    item.get("note", "").strip(),
                    item_id,
                    user_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT id, context, opening, status, note
                FROM repertoire_items WHERE id = ? AND user_id = ?
                """,
                (item_id, user_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def delete_repertoire_item(self, user_id: int, item_id: int) -> bool:
        """Delete one saved opening-plan entry owned by a user."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM repertoire_items WHERE id = ? AND user_id = ?",
                (item_id, user_id),
            )
        return cursor.rowcount > 0

    def list_user_profiles(self) -> list[dict[str, object]]:
        """Return all local user profiles."""
        with self._connect() as connection:
            user_ids = [
                int(row["id"])
                for row in connection.execute("SELECT id FROM users ORDER BY id")
            ]
        return [
            profile
            for user_id in user_ids
            if (profile := self.get_user_profile(user_id)) is not None
        ]

    @staticmethod
    def _user_game_filter(
        user_id: int,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        color: str | None = None,
    ) -> tuple[str, list[object]]:
        clauses = ["link.user_id = ?"]
        parameters: list[object] = [user_id]
        if date_from:
            clauses.append("game.date >= ?")
            parameters.append(date_from)
        if date_to:
            clauses.append("game.date <= ?")
            parameters.append(date_to)
        if color:
            clauses.append("link.player_color = ?")
            parameters.append(color)
        return " AND ".join(clauses), parameters

    def get_user_overview(
        self,
        user_id: int,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        color: str | None = None,
        grouping: str = "family",
        opening_limit: int = 10,
    ) -> dict[str, object] | None:
        """Calculate result and rating statistics from one user's perspective."""
        profile = self.get_user_profile(user_id)
        if profile is None:
            return None

        where, parameters = self._user_game_filter(
            user_id, date_from=date_from, date_to=date_to, color=color
        )
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS total_games,
                    COALESCE(SUM(CASE WHEN link.player_color = 'white' THEN 1 ELSE 0 END), 0) AS white_games,
                    COALESCE(SUM(CASE WHEN link.player_color = 'black' THEN 1 ELSE 0 END), 0) AS black_games,
                    COALESCE(SUM(CASE
                        WHEN (link.player_color = 'white' AND game.result = '1-0')
                          OR (link.player_color = 'black' AND game.result = '0-1')
                        THEN 1 ELSE 0 END), 0) AS wins,
                    COALESCE(SUM(CASE WHEN game.result = '1/2-1/2' THEN 1 ELSE 0 END), 0) AS draws,
                    COALESCE(SUM(CASE
                        WHEN (link.player_color = 'white' AND game.result = '0-1')
                          OR (link.player_color = 'black' AND game.result = '1-0')
                        THEN 1 ELSE 0 END), 0) AS losses,
                    COALESCE(SUM(CASE WHEN game.opening IS NOT NULL THEN 1 ELSE 0 END), 0) AS classified_games,
                    MIN(game.date) AS first_game_date,
                    MAX(game.date) AS last_game_date,
                    MIN(CASE
                        WHEN link.player_color = 'white' THEN game.white_elo
                        ELSE game.black_elo END) AS minimum_rating,
                    MAX(CASE
                        WHEN link.player_color = 'white' THEN game.white_elo
                        ELSE game.black_elo END) AS maximum_rating
                FROM user_games AS link
                JOIN games AS game ON game.id = link.game_id
                WHERE {where}
                """,
                parameters,
            ).fetchone()

        return {
            "user": profile,
            **dict(row),
            "top_openings": self.get_user_openings(
                user_id,
                date_from=date_from,
                date_to=date_to,
                color=color,
                grouping=grouping,
                limit=opening_limit,
            ),
        }

    def get_user_openings(
        self,
        user_id: int,
        limit: int = 10,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        color: str | None = None,
        grouping: str = "variation",
    ) -> list[dict[str, object]]:
        """Return a user's most-played classified openings with perspective results."""
        where, parameters = self._user_game_filter(
            user_id, date_from=date_from, date_to=date_to, color=color
        )
        opening_expression = "game.opening"
        eco_expression = "game.eco"
        group_expression = "game.eco, game.opening"
        if grouping == "family":
            opening_expression = """CASE
                WHEN INSTR(game.opening, ':') > 0
                THEN SUBSTR(game.opening, 1, INSTR(game.opening, ':') - 1)
                ELSE game.opening END"""
            eco_expression = "MIN(game.eco)"
            group_expression = opening_expression
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    {eco_expression} AS eco,
                    {opening_expression} AS opening,
                    COUNT(*) AS games,
                    SUM(CASE
                        WHEN (link.player_color = 'white' AND game.result = '1-0')
                          OR (link.player_color = 'black' AND game.result = '0-1')
                        THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN game.result = '1/2-1/2' THEN 1 ELSE 0 END) AS draws,
                    SUM(CASE
                        WHEN (link.player_color = 'white' AND game.result = '0-1')
                          OR (link.player_color = 'black' AND game.result = '1-0')
                        THEN 1 ELSE 0 END) AS losses
                FROM user_games AS link
                JOIN games AS game ON game.id = link.game_id
                WHERE {where} AND game.opening IS NOT NULL
                GROUP BY {group_expression}
                ORDER BY games DESC, opening
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_user_adjusted_openings(
        self,
        user_id: int,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        color: str | None = None,
        grouping: str = "family",
        min_games: int = 8,
    ) -> list[dict[str, object]] | None:
        """Compare opening results with the score implied by rating differences.

        This deliberately uses the standard Elo expectation game by game rather
        than treating all opponents in an opening as equally strong.  The
        confidence interval is for the mean game-level residual, so it conveys
        sample uncertainty without claiming that the opening caused the result.
        """
        if self.get_user_profile(user_id) is None:
            return None

        where, parameters = self._user_game_filter(
            user_id, date_from=date_from, date_to=date_to, color=color
        )
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT game.eco, game.opening, game.result, game.white_elo,
                       game.black_elo, link.player_color
                FROM user_games AS link
                JOIN games AS game ON game.id = link.game_id
                WHERE {where}
                  AND game.opening IS NOT NULL
                  AND game.result IN ('1-0', '0-1', '1/2-1/2')
                  AND game.white_elo IS NOT NULL
                  AND game.black_elo IS NOT NULL
                """,
                parameters,
            ).fetchall()

        groups: dict[tuple[str, str], dict[str, object]] = {}
        for row in rows:
            opening = str(row["opening"])
            if grouping == "family":
                opening = opening.split(":", 1)[0]
            player_color = str(row["player_color"])
            key = (opening, player_color)
            group = groups.setdefault(
                key,
                {"eco": row["eco"], "residuals": [], "actual_scores": [], "expected_scores": []},
            )
            player_rating = int(row["white_elo"] if player_color == "white" else row["black_elo"])
            opponent_rating = int(row["black_elo"] if player_color == "white" else row["white_elo"])
            expected = 1 / (1 + 10 ** ((opponent_rating - player_rating) / 400))
            result = str(row["result"])
            actual = 0.5 if result == "1/2-1/2" else (
                1.0 if (player_color == "white") == (result == "1-0") else 0.0
            )
            group["expected_scores"].append(expected)  # type: ignore[union-attr]
            group["actual_scores"].append(actual)  # type: ignore[union-attr]
            group["residuals"].append(actual - expected)  # type: ignore[union-attr]

        adjusted: list[dict[str, object]] = []
        for (opening, player_color), group in groups.items():
            residuals: list[float] = group["residuals"]  # type: ignore[assignment]
            games = len(residuals)
            if games < min_games:
                continue
            mean_residual = sum(residuals) / games
            if games > 1:
                variance = sum((residual - mean_residual) ** 2 for residual in residuals) / (games - 1)
                margin = 1.96 * math.sqrt(variance / games)
            else:
                margin = 0.0
            actual_scores: list[float] = group["actual_scores"]  # type: ignore[assignment]
            expected_scores: list[float] = group["expected_scores"]  # type: ignore[assignment]
            adjusted.append({
                "eco": group["eco"],
                "opening": opening,
                "color": player_color,
                "games": games,
                "actual_score": sum(actual_scores) / games,
                "expected_score": sum(expected_scores) / games,
                "adjusted_score": mean_residual,
                "confidence_low": mean_residual - margin,
                "confidence_high": mean_residual + margin,
                "reliability": "reliable" if games >= 30 else "limited",
            })
        return sorted(adjusted, key=lambda item: (-float(item["adjusted_score"]), -int(item["games"])))

    def get_user_responses_to_first_move(
        self,
        user_id: int,
        first_move: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        color: str | None = None,
        limit: int = 8,
    ) -> list[dict[str, object]]:
        """Group opponents' first replies after one White first move."""
        if color == "black":
            return []
        where, parameters = self._user_game_filter(
            user_id, date_from=date_from, date_to=date_to, color="white"
        )
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT game.pgn, game.result
                FROM user_games AS link
                JOIN games AS game ON game.id = link.game_id
                WHERE {where}
                """,
                parameters,
            ).fetchall()

        responses: dict[str, dict[str, int]] = {}
        for row in rows:
            game = chess.pgn.read_game(io.StringIO(str(row["pgn"])))
            if game is None:
                continue
            board = game.board()
            moves = iter(game.mainline_moves())
            white_move = next(moves, None)
            black_move = next(moves, None)
            if white_move is None or black_move is None:
                continue
            white_san = board.san(white_move)
            board.push(white_move)
            black_san = board.san(black_move)
            if white_san != first_move:
                continue
            response = responses.setdefault(black_san, {"games": 0, "wins": 0, "draws": 0, "losses": 0})
            response["games"] += 1
            if row["result"] == "1-0":
                response["wins"] += 1
            elif row["result"] == "1/2-1/2":
                response["draws"] += 1
            else:
                response["losses"] += 1

        return [
            {"reply": reply, **results}
            for reply, results in sorted(
                responses.items(), key=lambda item: (-item[1]["games"], item[0])
            )[:limit]
        ]

    def get_user_opening_detail(
        self,
        user_id: int,
        family: str,
        recent_limit: int = 12,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        color: str | None = None,
    ) -> dict[str, object] | None:
        """Return color, variation, yearly, and recent-game data for an opening family."""
        profile = self.get_user_profile(user_id)
        family = family.strip()
        if profile is None or not family:
            return None

        escaped_family = family.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        opening_parameters = (family, f"{escaped_family}:%")
        where, filter_parameters = self._user_game_filter(
            user_id, date_from=date_from, date_to=date_to, color=color
        )
        result_columns = """
            COUNT(*) AS games,
            SUM(CASE
                WHEN (link.player_color = 'white' AND game.result = '1-0')
                  OR (link.player_color = 'black' AND game.result = '0-1')
                THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN game.result = '1/2-1/2' THEN 1 ELSE 0 END) AS draws,
            SUM(CASE
                WHEN (link.player_color = 'white' AND game.result = '0-1')
                  OR (link.player_color = 'black' AND game.result = '1-0')
                THEN 1 ELSE 0 END) AS losses
        """
        opening_filter = "(game.opening = ? OR game.opening LIKE ? ESCAPE '\\')"

        with self._connect() as connection:
            total = connection.execute(
                f"""
                SELECT {result_columns}
                FROM user_games AS link
                JOIN games AS game ON game.id = link.game_id
                WHERE {where} AND {opening_filter}
                """,
                (*filter_parameters, *opening_parameters),
            ).fetchone()
            if total is None or int(total["games"]) == 0:
                return None

            colors = connection.execute(
                f"""
                SELECT link.player_color AS color, {result_columns}
                FROM user_games AS link
                JOIN games AS game ON game.id = link.game_id
                WHERE {where} AND {opening_filter}
                GROUP BY link.player_color
                ORDER BY link.player_color DESC
                """,
                (*filter_parameters, *opening_parameters),
            ).fetchall()
            variations = connection.execute(
                f"""
                SELECT game.eco, game.opening, {result_columns}
                FROM user_games AS link
                JOIN games AS game ON game.id = link.game_id
                WHERE {where} AND {opening_filter}
                GROUP BY game.eco, game.opening
                ORDER BY games DESC, game.opening
                """,
                (*filter_parameters, *opening_parameters),
            ).fetchall()
            years = connection.execute(
                f"""
                SELECT SUBSTR(game.date, 1, 4) AS year, {result_columns}
                FROM user_games AS link
                JOIN games AS game ON game.id = link.game_id
                WHERE {where} AND game.date IS NOT NULL AND {opening_filter}
                GROUP BY SUBSTR(game.date, 1, 4)
                ORDER BY year
                """,
                (*filter_parameters, *opening_parameters),
            ).fetchall()
            recent_games = connection.execute(
                f"""
                SELECT
                    game.date, game.white, game.black, game.result,
                    game.time_control, game.eco, game.opening,
                    game.source_url, link.player_color
                FROM user_games AS link
                JOIN games AS game ON game.id = link.game_id
                WHERE {where} AND {opening_filter}
                ORDER BY game.date DESC, game.id DESC
                LIMIT ?
                """,
                (*filter_parameters, *opening_parameters, recent_limit),
            ).fetchall()

        return {
            "user": profile,
            "family": family,
            **dict(total),
            "colors": [dict(row) for row in colors],
            "variations": [dict(row) for row in variations],
            "years": [dict(row) for row in years],
            "recent_games": [dict(row) for row in recent_games],
        }

    @staticmethod
    def _practice_position(row: sqlite3.Row) -> dict[str, object]:
        position = dict(row)
        for field in ("line", "san_path", "examples"):
            position[field] = json.loads(position[field])
        return position

    def list_practice_positions(self, user_id: int) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM practice_positions WHERE user_id = ? ORDER BY id DESC", (user_id,)
            ).fetchall()
        return [self._practice_position(row) for row in rows]

    def get_practice_position(self, user_id: int, position_id: int) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM practice_positions WHERE user_id = ? AND id = ?", (user_id, position_id)
            ).fetchone()
        return self._practice_position(row) if row is not None else None

    def save_practice_position(self, user_id: int, position: dict) -> tuple[dict, bool]:
        """Create a bookmark, preserving existing notes on duplicate saves."""
        columns = ("position_key", "fen", "family", "player_color", "line", "san_path",
                   "date_from", "date_to", "note", "candidate_move", "examples")
        values = [json.dumps(position[key]) if key in {"line", "san_path", "examples"}
                  else position[key] for key in columns]
        with self._connect() as connection:
            cursor = connection.execute(
                f"""INSERT INTO practice_positions (user_id, {', '.join(columns)})
                VALUES ({', '.join('?' for _ in range(len(columns) + 1))})
                ON CONFLICT(user_id, position_key, player_color) DO NOTHING""",
                [user_id, *values],
            )
            created = cursor.rowcount == 1
            row = connection.execute(
                """SELECT * FROM practice_positions
                WHERE user_id = ? AND position_key = ? AND player_color = ?""",
                (user_id, position["position_key"], position["player_color"]),
            ).fetchone()
        return self._practice_position(row), created

    def update_practice_position(self, user_id: int, position_id: int, note: str, candidate_move: str) -> dict | None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE practice_positions SET note = ?, candidate_move = ? WHERE user_id = ? AND id = ?",
                (note, candidate_move, user_id, position_id),
            )
        return self.get_practice_position(user_id, position_id)

    def delete_practice_position(self, user_id: int, position_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM practice_positions WHERE user_id = ? AND id = ?", (user_id, position_id)
            )
        return cursor.rowcount == 1

    def get_explorer_games(
        self, user_id: int, *, color: str,
        date_from: str | None = None, date_to: str | None = None,
    ) -> list[dict[str, object]]:
        """Read the scoped archive, including games ultimately classified elsewhere."""
        where, parameters = self._user_game_filter(
            user_id, date_from=date_from, date_to=date_to, color=color
        )
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT game.pgn, game.result, game.date, game.source_url
                FROM user_games AS link JOIN games AS game ON game.id = link.game_id
                WHERE {where} ORDER BY game.date DESC, game.id DESC""",
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_opening_reference_game(
        self,
        user_id: int,
        family: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        color: str | None = None,
    ) -> dict[str, object] | None:
        """Return one common classified position to represent an opening family."""
        escaped_family = family.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where, parameters = self._user_game_filter(
            user_id, date_from=date_from, date_to=date_to, color=color
        )
        opening_filter = "(game.opening = ? OR game.opening LIKE ? ESCAPE '\\')"
        with self._connect() as connection:
            variation = connection.execute(
                f"""
                SELECT game.opening
                FROM user_games AS link
                JOIN games AS game ON game.id = link.game_id
                WHERE {where} AND {opening_filter}
                GROUP BY game.opening
                ORDER BY COUNT(*) DESC, game.opening
                LIMIT 1
                """,
                (*parameters, family, f"{escaped_family}:%"),
            ).fetchone()
            if variation is None:
                return None
            row = connection.execute(
                f"""
                SELECT game.opening, game.opening_ply, game.pgn, link.player_color
                FROM user_games AS link
                JOIN games AS game ON game.id = link.game_id
                WHERE {where} AND game.opening = ?
                ORDER BY game.id DESC
                LIMIT 1
                """,
                (*parameters, variation["opening"]),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_recent_opening_losses(self, user_id: int, family: str, *, date_from: str | None = None, date_to: str | None = None, color: str | None = None, limit: int = 3) -> list[dict[str, object]]:
        """Return a few recent losses with their PGNs for focused engine review."""
        escaped = family.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where, parameters = self._user_game_filter(user_id, date_from=date_from, date_to=date_to, color=color)
        with self._connect() as connection:
            rows = connection.execute(f"""
                SELECT game.date, game.white, game.black, game.source_url, game.pgn, link.player_color
                FROM user_games AS link JOIN games AS game ON game.id = link.game_id
                WHERE {where} AND (game.opening = ? OR game.opening LIKE ? ESCAPE '\\')
                  AND ((link.player_color = 'white' AND game.result = '0-1') OR (link.player_color = 'black' AND game.result = '1-0'))
                ORDER BY game.date DESC, game.id DESC LIMIT ?
            """, (*parameters, family, f"{escaped}:%", limit)).fetchall()
        return [dict(row) for row in rows]

    def get_recent_losses(self, user_id: int, *, date_from: str | None = None, date_to: str | None = None, color: str | None = None, limit: int = 6) -> list[dict[str, object]]:
        """Return a small, recent loss sample for cross-game tactical analysis."""
        where, parameters = self._user_game_filter(user_id, date_from=date_from, date_to=date_to, color=color)
        with self._connect() as connection:
            rows = connection.execute(f"""
                SELECT game.date, game.white, game.black, game.source_url, game.pgn, link.player_color
                FROM user_games AS link JOIN games AS game ON game.id = link.game_id
                WHERE {where} AND ((link.player_color = 'white' AND game.result = '0-1') OR (link.player_color = 'black' AND game.result = '1-0'))
                ORDER BY game.date DESC, game.id DESC LIMIT ?
            """, (*parameters, limit)).fetchall()
        return [dict(row) for row in rows]

    def backfill_openings(self, catalog: object) -> tuple[int, int]:
        """Classify stored games missing opening metadata."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, pgn FROM games
                WHERE eco IS NULL OR opening IS NULL
                ORDER BY id
                """
            ).fetchall()
            games_updated = 0
            games_unclassified = 0
            for row in rows:
                match = catalog.classify_pgn(row["pgn"])
                if match is None:
                    games_unclassified += 1
                    continue
                connection.execute(
                    """
                    UPDATE games
                    SET eco = COALESCE(eco, ?),
                        opening = COALESCE(opening, ?),
                        opening_ply = ?
                    WHERE id = ?
                    """,
                    (match.eco, match.name, match.ply, row["id"]),
                )
                games_updated += 1

        return games_updated, games_unclassified

    def count_games(self, *, owner_user_id: int | None = None) -> int:
        """Return the number of stored games without loading their records."""
        with self._connect() as connection:
            query = "SELECT COUNT(*) AS total FROM games"
            if owner_user_id is not None:
                row = connection.execute(query + " WHERE owner_user_id = ?", (owner_user_id,)).fetchone()
            else:
                row = connection.execute(query).fetchone()
        return int(row["total"])

    def list_games(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        owner_user_id: int | None = None,
    ) -> list[GameRecord]:
        """Return stored games in import order, optionally as a bounded page."""
        columns = ", ".join(GAME_COLUMNS)
        query = f"SELECT {columns} FROM games"
        parameters: tuple[int, ...] = ()
        if owner_user_id is not None:
            query += " WHERE owner_user_id = ?"
            parameters = (owner_user_id,)
        query += " ORDER BY id DESC" if owner_user_id is not None else " ORDER BY id"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            parameters = (*parameters, limit, offset)

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()

        return [GameRecord(**dict(row)) for row in rows]
