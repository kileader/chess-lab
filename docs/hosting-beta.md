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

- One chess identity per account during onboarding. It describes imported games;
  it does not prove ownership of a Lichess/Chess.com account.
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
