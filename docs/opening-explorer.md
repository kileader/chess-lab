# Opening explorer

The opening detail page includes a position-based explorer backed by
`GET /api/users/{user_id}/openings/explorer`.

## Scope and counting

- `family` selects the shortest defining move line in the opening catalog.
- `color` is required: every result is from that user's White or Black perspective.
- Optional `date_from` and `date_to` retain the dashboard's inclusive date scope.
- `line` is a comma-separated legal UCI continuation from the defining position,
  limited to 24 half-moves. The API provides SAN labels and a FEN for display.
- All linked games in that date/color scope are searched, not just those whose
  final classification matches the family. This avoids losing games later
  classified as another opening.
- Position identity includes piece placement, side to move, castling rights,
  and legal en-passant availability. Move counters are not part of identity.
- Each game counts at its first visit to a position within its first 40 moves.
  Transpositions are included. A clicked position may therefore include games
  arriving by other paths, not just games following the displayed move sequence.

## Results and limitations

Reply frequency divides branch games by all games reaching the position.
Games ending there have no reply, so frequencies can total less than 100%.
Final-game score is `(wins + draws / 2) / completed games`; unfinished games
contribute to frequency but not to score. The score change is relative to all
completed games at the parent position, not an engine evaluation or causal effect.

The review note flags branches with at least eight completed games and a score
at least ten percentage points below the position's overall score. This is a
descriptive screening rule, not a statistical significance test. Opponent
strength, later mistakes, and selection effects are not controlled for.

Malformed PGNs are excluded and their count is reported. Parsed position maps
are cached by PGN content (at most 8,192 games); no user results are cached.
The first request can take several seconds; subsequent exploration reuses the
maps. New imports are included on the next request without cache invalidation.

Regression coverage is in `tests/test_explorer.py` and `tests/test_api.py`.

## Saved practice positions

The explorer's save form stores the exact FEN, defining opening and UCI
continuation, player color, date scope, optional note and legal SAN move to try,
and up to three example-game links. The optional move is for the side to move,
which may be the opponent. It is a personal study idea, not an engine suggestion.

`/api/users/{user_id}/practice-positions` supports GET and POST; its `/{id}`
routes support PATCH (note and move) and DELETE. SQLite creates the additive
`practice_positions` table on connection. Saves survive restarts. Position
identity excludes move counters and is unique per user and player color;
duplicate saves return the original entry without overwriting notes or scope.

The Repertoire page displays saved boards and supports editing and removal.
“Return to explorer” restores the saved continuation, color, and date scope;
the statistics are recalculated from the current archive. Example links are
snapshots from save time. Removing a position never removes imported games.
