# F405 Live Leaderboard

A live, public ranking of every student's BTC weekly-options bot, sorted by
**risk-adjusted return** with a prominent **💀 BLEW UP** badge for any bot that got
liquidated or fell below 25% of its starting equity. The whole point: the game
rewards *survival*, not gambling.

```
leaderboard/
  schema.sql              Turso/libSQL tables: students, equity_snapshots, scores
  poller/poll.py          15-min poller: read Deribit testnet -> score -> Turso
  poller/roster.example.json   roster shape (copy to roster.json, add read-only keys)
  web/                    Next.js (App Router) app, deploys to Vercel, reads Turso
../.github/workflows/poll-leaderboard.yml   the cron that runs the poller
```

How it fits together:

```
Deribit testnet  --(read-only key)-->  poller (GitHub Actions, every 15 min)
                                          |  computes equity + risk-adjusted score
                                          v
                                        Turso (libSQL)
                                          ^
                                          |  reads standings + sparkline series
                                        Next.js app on Vercel  -->  students' browsers
```

The scoring in `poller/poll.py` is identical to `score.py`:

```
risk_adjusted = total_return / max(max_drawdown, 0.02)
blew_up       = liquidated at any point OR equity ever < 25% of the baseline
```

Verify the math offline (no network, no DB) with:

```bash
uv run python leaderboard/poller/poll.py --self-test
```

---

## Why read-only keys are safe

Each student creates a **read-only** API key on the Deribit *testnet*
(test.deribit.com). A read-only key can fetch the account balance but **cannot
place or cancel orders**, so even though the poller holds many students' keys it
can never trade on anyone's behalf. Keys live in GitHub Actions secrets, never in
the repo.

---

## Deploy — copy/paste

### 1. Create the Turso database

```bash
# install once: https://docs.turso.tech/cli/installation
curl -sSfL https://get.tur.so/install.sh | bash
turso auth login

# create the DB and load the schema
turso db create f405-leaderboard
turso db shell f405-leaderboard < leaderboard/schema.sql

# grab the two values the app + poller need
turso db show f405-leaderboard --url        # -> TURSO_DATABASE_URL (libsql://...)
turso db tokens create f405-leaderboard      # -> TURSO_AUTH_TOKEN
```

### 2. Build the roster (read-only keys)

Each student creates a **read-only** key at test.deribit.com → Account → API, then
sends you the `client_id` / `client_secret`. Assemble them into one JSON array
(see `poller/roster.example.json`):

```json
[
  { "id": "ada-lovelace", "name": "Ada Lovelace", "team": "Section A",
    "start_equity_usd": 100000,
    "client_id": "RO_ID", "client_secret": "RO_SECRET" }
]
```

You can paste keys inline (as above) **or** keep the committed roster secret-free
by using `"client_id_env": "DERIBIT_RO_ADA_ID"` and adding that env var as its own
secret. The committed `roster.json` is git-ignored regardless.

### 3. Add GitHub repo secrets (Settings → Secrets and variables → Actions)

| Secret | Value |
| --- | --- |
| `TURSO_DATABASE_URL` | from `turso db show --url` |
| `TURSO_AUTH_TOKEN` | from `turso db tokens create` |
| `ROSTER_JSON` | the whole roster array from step 2 (read-only keys inline) |

The workflow `.github/workflows/poll-leaderboard.yml` already runs every 15 minutes
and on the **Run workflow** button. Trigger it once manually to confirm it polls
and writes rows.

### 4. Deploy the web app to Vercel (free)

```bash
# from the repo root
cd leaderboard/web
npm i -g vercel    # if you don't have it
vercel              # link/create the project
```

In the Vercel project → **Settings → Environment Variables**, add:

| Variable | Value |
| --- | --- |
| `TURSO_DATABASE_URL` | same libsql:// URL as above |
| `TURSO_AUTH_TOKEN` | same token as above |

Then deploy production:

```bash
vercel --prod
```

> Set Vercel's **Root Directory** to `leaderboard/web` if you import the repo
> through the dashboard instead of the CLI.

### 5. Done

- The poller fills `equity_snapshots` + `scores` every 15 minutes.
- The Vercel app renders the live ranking (it uses `force-dynamic`, so every page
  load reflects the latest poll) with an equity sparkline and the 💀 badge.

---

## Local development

```bash
cd leaderboard/web
pnpm install          # or npm install
cp .env.example .env.local   # fill in the two Turso values
pnpm dev              # http://localhost:3000
```

Run the poller locally against your DB:

```bash
export TURSO_DATABASE_URL=libsql://...
export TURSO_AUTH_TOKEN=...
export ROSTER_JSON='[{"id":"me","name":"Me","client_id":"...","client_secret":"..."}]'
uv run --with httpx python leaderboard/poller/poll.py
```
