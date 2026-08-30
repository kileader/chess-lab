# Chess Lab Architecture

## Status

Accepted as the intended direction. This document does not configure or perform a deployment.

The private-beta implementation and required provider setup are documented in
[hosting-beta.md](hosting-beta.md). Google sign-in uses Supabase Auth; application
data stays in Railway PostgreSQL. Deployment and real OAuth verification remain
separate launch gates, not something a successful local build proves.

## Deployment boundary

Chess Lab will be split into two deployable applications while keeping one repository:

```text
Vercel frontend
    |
    | HTTPS: JSON responses and multipart PGN uploads
    v
Railway Python API
    |
    | calls reusable Python functions
    v
chesslab core package
    |
    | SQL
    v
Railway PostgreSQL
```

The frontend will never connect directly to the database. The Python API will own PGN parsing,
data cleaning, validation, persistence, and analytics.

## Responsibilities

### Core package: `chesslab/`

- Parse raw PGN data.
- Convert parsed games into structured records.
- Clean and validate chess metadata.
- Derive player-perspective and analytical fields.
- Remain usable from tests, scripts, and the future API without importing UI code.

### Python API on Railway

- Use FastAPI as a thin HTTP layer around `chesslab` functions.
- Accept PGN uploads and player-selection input.
- Manage database transactions.
- Return JSON records and analytical results.
- Restrict browser access to configured frontend origins.

### Frontend on Vercel

- Select and upload PGN files directly to the Railway API.
- Display import results, tables, filters, statistics, and charts.
- Keep chess rules, PGN parsing, and analytical calculations out of UI components.
- Read the Railway API base URL from environment configuration.

## Intended repository shape

The existing files should remain in place until a feature actually requires a new boundary.
The likely shape is:

```text
chess-lab/
|-- chesslab/       # Existing reusable Python core
|-- backend/        # Future FastAPI entry point and backend configuration
|-- frontend/       # Future Vercel frontend
|-- tests/          # Core and backend tests
|-- data/           # Local sample data only
|-- docs/
`-- main.py         # Current local entry point
```

## Database strategy

SQLite remains useful for learning SQL and building the first local persistence layer. Before a
public web deployment, production storage should move to Railway PostgreSQL and use its
`DATABASE_URL` environment variable.

This avoids coupling production data to the filesystem of one backend instance. Railway volumes
can persist SQLite, but volume-backed services cannot use replicas and may have brief downtime
during redeployment. PostgreSQL is the intended production database; SQLite is the local learning
and test database.

Database access should live in a small Python storage module rather than in FastAPI route handlers
or frontend code. We will introduce an ORM or database toolkit only when persistence work begins.

## Request and data flow

```text
PGN file
  -> browser upload
  -> FastAPI endpoint
  -> chesslab.importer.load_games()
  -> chesslab.importer.game_to_record()
  -> validation and duplicate handling
  -> database transaction
  -> JSON response
  -> frontend table or chart
```

For larger uploads, the browser should send the file directly to Railway rather than routing the
file through a Vercel server function.

## Configuration and security

- Database credentials stay in Railway environment variables and are never exposed to the browser.
- The frontend receives only a public API base URL through Vercel environment configuration.
- The backend will use an explicit allowed-origin setting for CORS.
- Local environment files and database files must remain ignored by Git.
- Uploaded filenames must not be treated as trusted filesystem paths.

## Deferred decisions

- Frontend framework and charting library.
- Authentication, if this becomes more than a private personal app.
- Stable game identifier and duplicate-detection policy.
- Database toolkit and migration system.
- Whether original PGN text should be retained after structured records are stored.
- Background jobs for analysis that becomes too slow for one HTTP request.

## Platform references

- [Railway FastAPI guide](https://docs.railway.com/guides/fastapi)
- [Railway PostgreSQL documentation](https://docs.railway.com/databases/postgresql)
- [Railway volume limitations](https://docs.railway.com/volumes/reference)
- [Vercel environment variables](https://vercel.com/docs/environment-variables)
- [Vercel CORS guidance](https://vercel.com/kb/guide/how-to-enable-cors)
