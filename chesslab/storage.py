"""SQLite persistence for structured Chess Lab game records."""

import sqlite3
from collections.abc import Iterable
from pathlib import Path

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
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS games_source_identity "
            "ON games(source, source_game_id) WHERE source_game_id IS NOT NULL"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS games_fingerprint "
            "ON games(fingerprint) WHERE fingerprint IS NOT NULL"
        )
        connection.execute(CREATE_USERS_TABLE)
        connection.execute(CREATE_PLAYER_IDENTITIES_TABLE)
        connection.execute(CREATE_USER_GAMES_TABLE)
        connection.execute(CREATE_REPERTOIRE_ITEMS_TABLE)
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
            INSERT OR IGNORE INTO user_games (user_id, game_id, player_color)
            SELECT
                identity.user_id,
                game.id,
                CASE
                    WHEN LOWER(game.white) = identity.username_normalized THEN 'white'
                    ELSE 'black'
                END
            FROM player_identities AS identity
            JOIN games AS game ON game.source = identity.platform
            WHERE LOWER(game.white) = identity.username_normalized
               OR LOWER(game.black) = identity.username_normalized
            """
        )

    def save_games(self, games: Iterable[GameRecord]) -> int:
        """Insert all supplied games in one transaction and return the count."""
        _, games_added = self.import_games(games)
        return games_added

    def import_games(self, games: Iterable[GameRecord]) -> tuple[int, int]:
        """Stream games through one transaction and return received/added counts."""
        placeholders = ", ".join("?" for _ in GAME_COLUMNS)
        columns = ", ".join(GAME_COLUMNS)
        insert_query = f"INSERT OR IGNORE INTO games ({columns}) VALUES ({placeholders})"
        games_received = 0
        games_added = 0

        with self._connect() as connection:
            for game in games:
                game_row = tuple(getattr(game, column) for column in GAME_COLUMNS)
                changes_before = connection.total_changes
                connection.execute(insert_query, game_row)
                games_received += 1
                games_added += connection.total_changes - changes_before
            self._link_games_to_identities(connection)

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
                    "INSERT INTO users (display_name) VALUES (?)",
                    (display_name.strip(),),
                )
                user_id = int(cursor.lastrowid)
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
                SELECT platform, username FROM player_identities
                WHERE user_id = ? ORDER BY id
                """,
                (user_id,),
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
                ORDER BY games DESC, game.opening
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
        return [dict(row) for row in rows]

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

    def count_games(self) -> int:
        """Return the number of stored games without loading their records."""
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM games").fetchone()
        return int(row[0])

    def list_games(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[GameRecord]:
        """Return stored games in import order, optionally as a bounded page."""
        columns = ", ".join(GAME_COLUMNS)
        query = f"SELECT {columns} FROM games ORDER BY id"
        parameters: tuple[int, ...] = ()
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            parameters = (limit, offset)

        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()

        return [GameRecord(**dict(row)) for row in rows]
