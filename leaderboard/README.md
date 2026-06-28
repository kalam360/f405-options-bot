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

These are the **exact** secret names the cron workflow
(`.github/workflows/poll-leaderboard.yml`) reads — they must match character for
character:

| Secret | Required? | Value |
| --- | --- | --- |
| `TURSO_DATABASE_URL` | **yes** | from `turso db show --url` (the `libsql://…` URL) |
| `TURSO_AUTH_TOKEN` | **yes** | from `turso db tokens create` |
| `ROSTER_JSON` | **yes** | the whole roster array from step 2 (read-only keys inline) |

**Deribit index source — no secret needed.** The poller reads the BTC index from
Deribit testnet's **public** endpoint (`public/get_index_price` on
`https://test.deribit.com`, hard-coded in `poll.py`). It needs no API key and no
secret — only each student's *read-only* account key, which is carried inside
`ROSTER_JSON` above. So those three secrets are the complete set.

The workflow already runs every 15 minutes and on the **Run workflow** button.
Trigger it once manually to confirm it polls and writes rows. If a single
student's key is bad or expired, the poller logs `SKIPPED` for that student and
keeps going — one bad key never aborts the whole run.

### 3b. (Optional) Seed demo data before real students register

So the leaderboard isn't empty during a demo or dry-run, seed three synthetic
students (a steady survivor, a higher-return-but-higher-drawdown survivor, and one
that blows up). It reuses `poll.py`'s Turso client and scoring, and is idempotent
(it clears `demo-*` rows first, and only ever touches `demo-*` rows):

```bash
export TURSO_DATABASE_URL=libsql://...
export TURSO_AUTH_TOKEN=...
uv run --with httpx python leaderboard/poller/seed_demo.py
```

Re-run any time; delete the demo rows later with
`DELETE FROM scores/equity_snapshots/students WHERE … LIKE 'demo-%'` (children
first) or just leave them — real student rows rank alongside them.

### Deploy order (summary)

1. Create the Turso DB + load `schema.sql` (step 1).
2. Build the roster with read-only keys (step 2).
3. Add the three GitHub secrets above (step 3).
4. *(optional)* Seed demo data (step 3b).
5. Deploy the web app to Vercel with the same two Turso env vars (step 4).
6. Trigger the workflow once to confirm rows land (step 5).

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
