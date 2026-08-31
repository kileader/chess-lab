CREATE TABLE community_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    public_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    bio TEXT NOT NULL DEFAULT '',
    visible INTEGER NOT NULL DEFAULT 0 CHECK(visible IN (0, 1))
);
CREATE TABLE community_games (
    public_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES community_profiles(user_id) ON DELETE CASCADE,
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    caption TEXT NOT NULL DEFAULT '',
    snapshot TEXT NOT NULL,
    shared_at TEXT NOT NULL,
    UNIQUE(user_id, game_id)
);
CREATE INDEX idx_community_games_recent ON community_games(shared_at, public_id);
