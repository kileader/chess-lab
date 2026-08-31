# Chess Lab

Understand your chess games, find openings worth studying, and keep track of what
to work on next.

Chess Lab turns your game history into a personal study workspace. Import games
from Lichess, Chess.com, or a PGN file, see how you perform with and against
different openings, and explore the moves behind those results.

**[Try the hosted beta](https://chess-lab-zeta.vercel.app)** — sign in with Google.

## What you can do

- **Import your games:** manually sync Lichess or Chess.com games by date and time
  control, or upload PGN files. Repeated imports skip games already saved.
- **See your opening results:** compare wins, draws, and losses from your side of
  the board, with the defining opening moves shown alongside their names.
- **Compare results against expectations:** rating-adjusted opening scores help
  distinguish your results from the strength of the opponents you faced.
- **Explore positions:** follow replies on an interactive board and see how games
  in your library continued, including positions reached through transpositions.
- **Build a study plan:** save repertoire notes and practice positions with a move
  you want to try.
- **Use multiple chess identities:** correct a username or add names from Lichess,
  Chess.com, and other PGN sources without re-uploading existing games.

## Accounts and imports

Your Google sign-in identifies your Chess Lab account. Your chess usernames identify
which side you played in imported games; they do not verify ownership of a chess
account or give access to another user's library.

Hosted libraries, statistics, and study notes are private. Multiple saved usernames
contribute to combined personal statistics. Games where neither side—or both
sides—matches your saved identities remain in your library but are excluded from
personal statistics.

Syncing is **user-triggered, not scheduled**. Click **Sync games** and keep the import
page open. Completed batches are saved, and an interrupted import can be retried.
Neither provider requires your chess password. Imports default to rapid games from
the last 90 days; other time controls are available.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js App Router, React, TypeScript |
| API | Python, FastAPI |
| Chess processing | python-chess and a reusable Python core |
| Storage | PostgreSQL in production; SQLite for local development |
| Authentication | Supabase Auth with Google sign-in |
| Hosting | Vercel frontend; Railway API and PostgreSQL |
| Tests | pytest, Node's test runner, PostgreSQL integration tests in GitHub Actions |

The frontend calls the API; it never connects directly to the database. Supabase
handles authentication, while application data lives in Railway PostgreSQL.

## Run locally

Prerequisites: Python 3.12, Node.js 22.13 or newer, and pnpm. Commands below use
PowerShell and start from the repository root.

### 1. Install backend dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### 2. Start the API in local-only mode

This uses a separate SQLite development database. No Supabase project or PostgreSQL
server is needed for a local PGN-based preview.

```powershell
$env:CHESSLAB_ENV = "development"
$env:CHESSLAB_AUTH_MODE = "local"
$env:CHESSLAB_LOCAL_USER_ID = "1"
$env:CHESSLAB_DATABASE_PATH = "data/chesslab-dev.db"
$env:DATABASE_URL = ""
$env:CHESSLAB_ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

The backend reads process environment variables; it does not automatically load a
root `.env` file. See [`.env.example`](.env.example) for the configuration reference.
Local authentication only accepts direct loopback requests and must never be used
for hosting.

### 3. Create a local profile

In a second terminal at the repository root, replace `YourChessUsername` with the
name used in your PGNs. Use `lichess` or `chess_com` for this legacy local endpoint.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/users `
  -ContentType "application/json" `
  -Body '{"display_name":"Local player","platform":"lichess","username":"YourChessUsername"}'
```

On a fresh database the returned profile ID is `1`. If using an existing database,
set `CHESSLAB_LOCAL_USER_ID` to the returned ID and restart the API.

### 4. Start the frontend

```powershell
cd frontend
pnpm install --frozen-lockfile
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
pnpm exec next dev --hostname 127.0.0.1 --port 3000
```

The example frontend configuration points to the local API and disables Google
sign-in. If you already have `.env.local`, check its values rather than overwriting
it. Open [the local app](http://127.0.0.1:3000) and upload a PGN to begin.
Interactive API documentation is at [localhost:8000/docs](http://127.0.0.1:8000/docs).

Provider syncing and hosted account settings require Supabase sign-in; they are not
enabled by the local-auth preview. For that setup, see the
[hosting and authentication guide](docs/hosting-beta.md).

The repository also retains Vinext preview scripts (`pnpm dev` / `pnpm build`).
The commands above use Next.js directly, matching the frontend framework deployed
on Vercel.

## Verification

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

PostgreSQL integration tests run when `CHESSLAB_TEST_POSTGRES_URL` points to a
dedicated test database; otherwise they are skipped. GitHub Actions provisions
PostgreSQL 17 and runs those tests too. Do not use your production database for tests.

From `frontend`:

```powershell
node --experimental-strip-types --test tests/security.test.mjs tests/chesscom-sync.test.mjs
pnpm run build:vercel
```

Despite its filename, `chesscom-sync.test.mjs` covers both import providers.

## Repository layout

```text
backend/         FastAPI routes, authentication, and migration entry points
chesslab/        PGN parsing, provider imports, storage, and chess analytics
frontend/        Next.js pages, interactive boards, and import UI
migrations/      Versioned PostgreSQL schema migrations
tests/           Python core, API, provider, and account-isolation tests
data/openings/   Opening reference dataset and its license
docs/            Hosting instructions and feature documentation
```

Local environment files and databases are ignored by Git. Never commit credentials,
production database URLs, or private game archives.

## Beta limitations

- No scheduled syncing or persistent background import jobs yet.
- No shared libraries, public profiles, or social feed.
- PGN uploads are limited to 10 MiB and 5,000 games per upload.
- Engine review is disabled in the hosted beta; opening statistics and saved study
  positions do not require an engine.
- Results describe your imported games, not the objective quality of an opening.
  Small samples, opponent strength, and mistakes later in a game affect outcomes.
- Further launch hardening includes abuse controls, account deletion/export, and a
  privacy policy. This is a working beta, not a production-readiness claim.

## Further documentation

- [Hosting, authentication, and private accounts](docs/hosting-beta.md)
- [Opening explorer: counting rules and limitations](docs/opening-explorer.md)
- [Opening dataset attribution](data/openings/README.md)

Opening reference data comes from `lichess-org/chess-openings` and is distributed
under CC0; its license is included in `data/openings/COPYING.txt`.
