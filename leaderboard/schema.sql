-- Leaderboard schema for Turso / libSQL (SQLite dialect).
--
-- Three tables:
--   students          one row per registered student/team (roster metadata only,
--                     NO secrets — the read-only Deribit keys live in env/secrets).
--   equity_snapshots  append-only time series; one row each time the poller runs.
--   scores            the current standings; one row per student, upserted each poll.
--
-- Apply with:  turso db shell <db-name> < leaderboard/schema.sql
-- (or in the web/Turso dashboard SQL console).

-- ---------------------------------------------------------------------------
-- Roster. `id` is a stable key you choose (e.g. the GitHub handle). The poller
-- upserts this from roster.json, so you normally don't edit it by hand.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS students (
    id                TEXT PRIMARY KEY,        -- stable id (e.g. github handle)
    name              TEXT NOT NULL,           -- display name
    github            TEXT,                    -- github handle (optional)
    team              TEXT,                    -- team/section label (optional)
    start_equity_usd  REAL,                    -- baseline; if NULL the first
                                               --   observed snapshot is the baseline
    created_at        INTEGER NOT NULL         -- ms since epoch
);

-- ---------------------------------------------------------------------------
-- Equity time series. The web app reads the recent tail of this per student to
-- draw the sparkline; the poller reads the whole series to compute drawdown.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  TEXT NOT NULL REFERENCES students(id),
    ts          INTEGER NOT NULL,              -- ms since epoch
    equity_usd  REAL NOT NULL,                 -- account equity marked to USD
    equity_btc  REAL NOT NULL,                 -- account equity in BTC (coin)
    index_usd   REAL NOT NULL,                 -- BTC index used for the USD convert
    liquidated  INTEGER NOT NULL DEFAULT 0     -- 0/1, equity collapsed to ~0
);

CREATE INDEX IF NOT EXISTS idx_snap_student_ts
    ON equity_snapshots (student_id, ts);

-- ---------------------------------------------------------------------------
-- Current standings — the table the leaderboard sorts on. One row per student,
-- replaced on every poll. risk_adjusted mirrors score.py exactly:
--     risk_adjusted = total_return / max(max_drawdown, 0.02)
-- blew_up = liquidated at any point OR equity ever fell below 25% of baseline.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scores (
    student_id     TEXT PRIMARY KEY REFERENCES students(id),
    ts             INTEGER NOT NULL,           -- ms epoch of the latest snapshot
    equity_usd     REAL NOT NULL,              -- latest equity
    start_equity_usd REAL NOT NULL,            -- baseline used
    total_return   REAL NOT NULL,              -- last/start - 1
    max_drawdown   REAL NOT NULL,              -- worst peak-to-trough, 0..1
    risk_adjusted  REAL NOT NULL,              -- the ranking metric
    blew_up        INTEGER NOT NULL DEFAULT 0, -- 0/1, gets the skull badge
    n_snapshots    INTEGER NOT NULL DEFAULT 0, -- history length (for transparency)
    updated_at     INTEGER NOT NULL            -- ms epoch when this row was written
);

-- Survivors first, then by the risk-adjusted metric. This is the canonical
-- leaderboard order; the web app uses the same ORDER BY.
CREATE INDEX IF NOT EXISTS idx_scores_rank
    ON scores (blew_up ASC, risk_adjusted DESC);
