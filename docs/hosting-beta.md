# Hosted beta with private accounts

## What is implemented

- Vercel builds the existing frontend with Next.js. Vinext remains available for
  local preview. No existing Sites metadata is removed or published.
- Supabase Auth performs Google OAuth with PKCE and cookie-backed SSR sessions.
- Railway runs FastAPI with PostgreSQL. The API validates bearer tokens directly
  with Supabase before trusting identity. It never trusts a browser-supplied user ID.
- Accounts are provisioned by stable Supabase user ID, never chess username or email.
- Every API user route checks ownership. Global user listing/creation is unavailable
  to signed-in hosted users. Imports, deduplication, examples, notes and plans are private.
- Anyone can register with a verified sign-in when `CHESSLAB_ALLOWED_EMAILS` is
  empty or unset. An optional server-side email allowlist can restrict access.
  Open registration does not expose libraries: no public social feed or automatic
  game sharing is enabled in this release.

## External setup required

These steps need access to Kevin's provider dashboards. Do not put secrets in chat
or commit local environment files. No paid resource has been provisioned by this work.

1. Create/select a Supabase project. Enable Google in Authentication → Providers.
   Configure a Google OAuth web client with the callback URI shown by Supabase.
   Disable unused sign-in methods and anonymous sign-in. Use Google's External
   audience and In production publishing status for launch. Google exempts basic
   identity-only scopes (`openid`, email, profile) from the testing user list;
   additional scopes may require test users or verification.
2. Supabase → URL configuration: set the production site URL and explicitly allow
   `https://<vercel-production-host>/auth/callback`. Avoid broad preview-host wildcards.
3. Vercel: import this repo with **Root Directory `frontend`**, Next.js framework,
   Node 22, and the checked-in `vercel.json` build command. Configure:
   - `NEXT_PUBLIC_CHESSLAB_AUTH_MODE=supabase`
   - `NEXT_PUBLIC_SUPABASE_URL=https://<project>.supabase.co`
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable key>` (never service role)
   - `NEXT_PUBLIC_SITE_URL=https://<vercel-production-host>` (no trailing slash)
   - `CHESSLAB_API_URL=https://<railway-api-host>`
   - `NEXT_PUBLIC_CHESSLAB_API_URL=https://<railway-api-host>`
4. Railway: confirm costs before adding the PostgreSQL service. Deploy the API
   from the repo root using `Dockerfile` and `railway.toml`. Configure:
   - `CHESSLAB_ENV=production`, `CHESSLAB_AUTH_MODE=supabase`
   - `DATABASE_URL` referencing Railway PostgreSQL's private connection URL
   - `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` matching the frontend
   - `CHESSLAB_ALLOWED_ORIGINS=https://<vercel-production-host>`
   - Leave `CHESSLAB_ALLOWED_EMAILS` unset or empty for open registration. Remove
     any existing list; a nonempty list still restricts sign-in to those emails.
   - `CHESSLAB_ENGINE_ENABLED=false`
5. Set Railway spend controls and PostgreSQL backups. The $5 subscription is not
   a hard cap on compute/database usage. No change to billing is automated here.

Public environment variables are compiled into the frontend; rebuild when changing
them. Supabase manages the Google client secret. The app does not need a service-role
key. Uploads go directly to Railway with a bearer token, not through Vercel functions.

Railway's pre-deploy command applies versioned PostgreSQL migrations transactionally,
under an advisory lock. Migrations never copy or expose the local database.
Production refuses local-auth bypass. Local preview remains direct loopback-only.

### Editable chess usernames

Signed-in users can open **Usernames** in the account menu (`/settings`) to correct
names, add Lichess, Chess.com, or Other identities, or remove obsolete names. At least one and
at most ten usernames are required. Multiple names on the same platform are allowed;
case-insensitive duplicates within a platform are rejected.
Other accepts PGN player names up to 80 printable characters (including spaces,
punctuation, and accents), matching only imports whose detected source is `other`.
It is not a wildcard for Lichess or Chess.com. Site usernames retain their existing
40-character letters/numbers/underscore/hyphen validation.

`PATCH /api/account/identities` accepts an `identities` list of `{platform, username}`.
The target account is always taken from the verified session, never the payload.
Saving atomically replaces that account's identities and rebuilds links for games
whose `owner_user_id` matches it. Imports and edits serialize on the account row.
The endpoint reports the number of owned games and the number matched to one side.
It does not delete games, repertoire plans, practice positions, or notes.

Only usernames on a game's source platform match. Games where neither player or
both players match remain in the private library, but are excluded from personal
statistics. Adding another person's name does not grant access to their library.
The user's own usernames contribute to combined stats; per-player libraries are not
implemented. Imports with zero single-side matches include a settings reminder.

Migration `002_multiple_chess_identities.sql` expands the PostgreSQL identity primary
key without deleting rows. Migration `003_other_chess_identities.sql` expands the
platform constraint while preserving identities. Ensure Railway's **Pre-deploy Command** is
`python -m backend.migrate` and verify `Database migrations complete.` before testing
the settings page. SQLite performs an atomic table-copy upgrade of older keys/checks.
PostgreSQL tests cover both fresh schemas and upgrading existing identity records.

### Manual Chess.com sync

Open **Import games** (`/import`), select a saved Chess.com username, choose dates
and a time control, then **Sync games**. Rapid and the last 90 days are selected
initially. Usernames settings also links directly to sync for each Chess.com name.
Only completed standard-chess games are imported. Both date endpoints are inclusive,
using the game's **end time in UTC** (which can differ from its PGN start date).
The dashboard's existing date filters are independent; the result links to all dates.

The backend calls Chess.com's public API without a password/token. A plan request
lists matching monthly archives; the browser then requests each month sequentially,
newest first. Keep the import page open. Stop finishes the current request and
prevents subsequent month requests. Successful months are committed to the verified
account's private library using the existing import/deduplication pipeline. There
is no shared library or account impersonation. An interrupted run can be retried;
it skips games already saved, including before an uncertain network response.

Endpoints: `POST /api/games/sync/chess-com/plan` and `/month`. Both require a saved
Chess.com identity belonging to the signed-in account; client-supplied owner IDs
are rejected. The month endpoint also validates its month against the chosen dates.
Provider URLs are never followed from archive payloads. Requests use a fixed HTTPS
host, no redirects, bounded timeouts and decoded response sizes, and no auth cookies
or tokens. Each month is fully parsed before writing, with a maximum of 20 MiB,
5,000 archive games and 128 KiB per selected PGN. Oversized months can still use
smaller PGN uploads. Invalid selected games abort that month without partial writes.

The current single-worker Railway service serializes outbound Chess.com requests
using a nonblocking process lock; concurrent requests or provider rate limits stop
with a retry message, retaining earlier completed months. Before scaling to multiple
workers/replicas, replace that guard with a shared provider queue/limiter. Chess.com's
caching can delay recent games. No scheduler, persistent sync job, additional service,
new environment variables, or database migration is needed for this release.
Scheduled syncing is not implemented; PGN uploads remain available.

### Manual Lichess sync

The same **Import games** page has a Lichess selector. Choose a saved Lichess username,
dates and time control (rapid by default). Settings links include the platform, so
the same name saved on both sites opens the correct importer. Only completed standard
games are saved. Unlike Chess.com, Lichess dates use game **creation/start time in UTC**.
The selected end date is inclusive; internally windows are `[since, until)` in milliseconds.

`POST /api/games/sync/lichess/plan` checks the public export for a first game in the
range and returns months to examine, newest first. `/month` downloads at most 201
games. Full batches split into two adjacent timestamp windows before saving; the
browser processes those sequentially until each contains at most 200 games. This
avoids silently truncating a busy month or losing tied timestamps. Each completed
batch is persisted; Stop prevents the next batch, and retries deduplicate saved games.
There is no background job. Keep the page open; navigating away stops further batches.

The provider uses anonymous NDJSON exports from a fixed HTTPS endpoint, with no
redirects or credentials, a serial process lock, time/size limits, and a 60-second
cooldown after HTTP 429. Direct exports are used without provider-side performance
filters, because those use Lichess's search index with different freshness/precision.
Speed and standard-chess filtering happen locally. Consequently a plan can contain
months with no games matching the chosen speed. The response has a 12 MiB limit,
each selected PGN has a 128 KiB limit, and invalid streams/games abort the batch.
No new credentials, service, schema changes, or environment variables are required.

## Preserve Kevin's current data

Leave the SQLite file in place and take a backup before transferring it. First sign
in to the hosted app as Kevin and verify the exact Supabase user ID in its dashboard.
The migration tool never assigns a local library merely because a login uses a
matching email, display name, or chess username.

Dry run (read-only, no database URL needed):

```powershell
.\.venv\Scripts\python.exe -m backend.migrate_local --source data/chesslab.db --local-user-id 1
```

After explicitly verifying the destination account, supply a secure `DATABASE_URL`
through the execution environment and use the same command with
`--auth-subject <verified-supabase-user-id> --apply`.

The copy is transactional and preserves existing destination entries. Re-running it
does not duplicate games or overwrite newer notes. It copies only the selected local
user's linked games, plan and saved positions, without deleting anything locally.
The destination's chess identity must match. Compare counts before inviting testers.

## Verification and launch gate

- `python -m pytest -q` runs SQLite/account security tests. PostgreSQL variants require
  `CHESSLAB_TEST_POSTGRES_URL`; without it they are explicitly skipped.
- The GitHub workflow provisions a disposable PostgreSQL 17 service and runs those
  variants too. It has not run until changes are pushed to an authorized repository.
- `pnpm run build:vercel` verifies the Vercel build.
- `node --experimental-strip-types --test tests/security.test.mjs` in `frontend`
  checks OAuth redirect and imported-link safety.
- Before inviting anyone: complete Google sign-in and sign-out using two real test
  accounts, exercise refresh/expired sessions, import separate archives, and verify
  neither account can read or edit the other's data by changing URLs/IDs.

Do not call this production-ready until PostgreSQL tests, actual OAuth, migration
counts and deployed cross-account checks pass.

## Beta constraints

- Onboarding starts with one chess identity; account settings supports up to ten.
  A username describes imported games, not verified ownership of a chess account.
- Maximum 10 MB and 5,000 games per import. Private imports are not a shared library.
- Expensive synchronous Stockfish endpoints are off for authenticated beta users.
  Opening results, adjusted scores, explorer and practice bookmarks do not need the
  engine. The production container deliberately does not bundle Stockfish. Adding
  engine jobs needs bounded execution, a Linux binary, and a resource budget first.
- Registration is open by default, but this remains a beta, not a production-readiness
  claim. Rate limits, abuse controls, account deletion/export, and a privacy policy
  remain launch-hardening work. Keep Railway spend controls and backups configured.

References: [Supabase Google login](https://supabase.com/docs/guides/auth/social-login/auth-google),
[Supabase SSR](https://supabase.com/docs/guides/auth/server-side/nextjs),
[Railway FastAPI](https://docs.railway.com/guides/fastapi),
[Railway PostgreSQL](https://docs.railway.com/databases/postgresql).
