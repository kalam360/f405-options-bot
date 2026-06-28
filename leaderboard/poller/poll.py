"""Leaderboard poller — runs on a 15-minute cron (GitHub Actions).

For every student on the roster (each with a *read-only* Deribit testnet API key):

  1. authenticate to the Deribit testnet,
  2. read their account summary (equity in BTC) and the BTC index,
  3. write an equity snapshot to Turso,
  4. recompute their risk-adjusted score + blow-up flag from the full history,
  5. upsert the standings row.

Read-only keys *cannot place orders*, so handing them to this poller is safe — the
worst it can do is read balances. Secrets never live in the repo: the roster file
holds only public metadata, and the keys arrive via environment variables.

The scoring here mirrors `score.py` exactly so the live leaderboard and the final
grade tell the same story:

    risk_adjusted = total_return / max(max_drawdown, 0.02)
    blew_up       = liquidated at any point OR equity ever < 25% of the baseline

Run it:
    # live (needs TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, and a roster with keys)
    uv run --with httpx python leaderboard/poller/poll.py

    # offline sanity check of the scoring math (no network, no DB)
    uv run python leaderboard/poller/poll.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field

# httpx is already a project dependency (see pyproject.toml). In CI we run this
# file with `uv run --with httpx` so the import is always satisfied.
try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - only hit if run without httpx
    httpx = None  # the --self-test path does not need the network


DERIBIT_BASE = "https://test.deribit.com"  # ALWAYS testnet for this course


# ===========================================================================
# Roster
# ===========================================================================
@dataclass
class Student:
    """One roster entry. Keys are read-only Deribit *testnet* credentials."""
    id: str
    name: str
    client_id: str
    client_secret: str
    github: str = ""
    team: str = ""
    start_equity_usd: float | None = None


def load_roster() -> list[Student]:
    """Load the roster from, in order of preference:

      * the ROSTER_JSON env var (a JSON array — the easy GitHub-secret path), or
      * the file at ROSTER_PATH (defaults to leaderboard/poller/roster.json).

    Each entry is {id, name, client_id, client_secret, github?, team?,
    start_equity_usd?}. See roster.example.json for the shape.
    """
    raw = os.environ.get("ROSTER_JSON")
    if raw:
        data = json.loads(raw)
    else:
        path = os.environ.get(
            "ROSTER_PATH",
            os.path.join(os.path.dirname(__file__), "roster.json"),
        )
        if not os.path.exists(path):
            return []
        with open(path) as fh:
            data = json.load(fh)

    students: list[Student] = []
    for row in data:
        # Allow keys to be given inline OR via named env vars (so the committed
        # roster.json can stay secret-free and point at GitHub secrets).
        client_id = row.get("client_id") or os.environ.get(row.get("client_id_env", ""), "")
        client_secret = row.get("client_secret") or os.environ.get(row.get("client_secret_env", ""), "")
        students.append(
            Student(
                id=row["id"],
                name=row.get("name", row["id"]),
                client_id=client_id,
                client_secret=client_secret,
                github=row.get("github", ""),
                team=row.get("team", ""),
                start_equity_usd=row.get("start_equity_usd"),
            )
        )
    return students


# ===========================================================================
# Deribit testnet (read-only)
# ===========================================================================
class Deribit:
    """Tiny read-only Deribit testnet REST client (auth + read calls only)."""

    def __init__(self, base_url: str = DERIBIT_BASE):
        self.base_url = base_url
        self._client = httpx.Client(base_url=base_url, timeout=20.0)

    def _get(self, path: str, params: dict, token: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = self._client.get(f"/api/v2/{path}", params=params, headers=headers)
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"Deribit error on {path}: {body['error']}")
        return body["result"]

    def index_price(self, currency: str = "BTC") -> float:
        result = self._get("public/get_index_price", {"index_name": f"{currency.lower()}_usd"})
        return float(result["index_price"])

    def auth(self, client_id: str, client_secret: str) -> str:
        result = self._get(
            "public/auth",
            {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        return result["access_token"]

    def account_summary(self, token: str, currency: str = "BTC") -> dict:
        return self._get("private/get_account_summary", {"currency": currency}, token=token)

    def close(self) -> None:
        self._client.close()


# ===========================================================================
# Turso / libSQL over the HTTP "pipeline" API (no extra dependency needed)
# ===========================================================================
class Turso:
    """Minimal Turso/libSQL HTTP client.

    Talks to the database's `/v2/pipeline` endpoint with a bearer token. We keep
    it dependency-light (httpx only) and expose a single `execute(sql, args)`
    that returns rows as dicts — enough for the poller's reads and upserts.
    """

    def __init__(self, url: str, auth_token: str):
        # Turso hands out libsql:// URLs; the HTTP API lives on https://.
        self.http_url = url.replace("libsql://", "https://").rstrip("/")
        self.auth_token = auth_token
        self._client = httpx.Client(timeout=30.0)

    @staticmethod
    def _encode(value) -> dict:
        if value is None:
            return {"type": "null", "value": None}
        if isinstance(value, bool):
            return {"type": "integer", "value": str(int(value))}
        if isinstance(value, int):
            return {"type": "integer", "value": str(value)}
        if isinstance(value, float):
            return {"type": "float", "value": value}
        return {"type": "text", "value": str(value)}

    @staticmethod
    def _decode(cell: dict):
        t = cell.get("type")
        v = cell.get("value")
        if t == "null":
            return None
        if t == "integer":
            return int(v)
        if t == "float":
            return float(v)
        return v  # text / blob -> str

    def execute(self, sql: str, args: list | None = None) -> list[dict]:
        """Run one statement; return result rows as a list of dicts."""
        stmt = {"sql": sql, "args": [self._encode(a) for a in (args or [])]}
        payload = {"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]}
        resp = self._client.post(
            f"{self.http_url}/v2/pipeline",
            headers={"Authorization": f"Bearer {self.auth_token}"},
            json=payload,
        )
        resp.raise_for_status()
        body = resp.json()
        first = body["results"][0]
        if first.get("type") != "ok":
            raise RuntimeError(f"Turso error: {first.get('error')}")
        result = first["response"]["result"]
        cols = [c["name"] for c in result["cols"]]
        return [
            {col: self._decode(cell) for col, cell in zip(cols, row)}
            for row in result["rows"]
        ]

    def close(self) -> None:
        self._client.close()


# ===========================================================================
# Scoring — identical math to score.py (kept here so the poller is standalone)
# ===========================================================================
@dataclass
class Score:
    total_return: float
    max_drawdown: float
    risk_adjusted: float
    blew_up: bool
    start_equity_usd: float
    last_equity_usd: float
    n: int


def compute_score(
    equity_series: list[float],
    liquidated_series: list[int] | None = None,
    start_equity_usd: float | None = None,
    blowup_floor: float = 0.25,
    dd_floor: float = 0.02,
) -> Score:
    """Risk-adjusted score from an equity time series (oldest -> newest).

    * total_return  = last / start - 1
    * max_drawdown  = worst peak-to-trough fraction over the path (0..1)
    * risk_adjusted = total_return / max(max_drawdown, dd_floor)
    * blew_up       = any liquidated flag OR equity ever < blowup_floor * start
    """
    series = [e for e in equity_series if e is not None]
    if not series:
        return Score(0.0, 0.0, 0.0, False, start_equity_usd or 0.0, 0.0, 0)

    start = start_equity_usd if start_equity_usd else series[0]
    last = series[-1]
    total_return = (last / start - 1.0) if start else 0.0

    peak = series[0]
    max_dd = 0.0
    for e in series:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    liq = any(liquidated_series or [])
    crashed = start > 0 and any(e < blowup_floor * start for e in series)
    blew_up = bool(liq or crashed)

    risk_adjusted = total_return / max(max_dd, dd_floor)
    return Score(total_return, max_dd, risk_adjusted, blew_up, start, last, len(series))


# ===========================================================================
# DB helpers
# ===========================================================================
def upsert_student(db: Turso, s: Student, now_ms: int) -> None:
    db.execute(
        """
        INSERT INTO students (id, name, github, team, start_equity_usd, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, github=excluded.github, team=excluded.team
        """,
        [s.id, s.name, s.github, s.team, s.start_equity_usd, now_ms],
    )


def insert_snapshot(db: Turso, student_id: str, ts: int, equity_usd: float,
                    equity_btc: float, index_usd: float, liquidated: bool) -> None:
    db.execute(
        """
        INSERT INTO equity_snapshots
            (student_id, ts, equity_usd, equity_btc, index_usd, liquidated)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [student_id, ts, equity_usd, equity_btc, index_usd, int(liquidated)],
    )


def read_history(db: Turso, student_id: str) -> tuple[list[float], list[int]]:
    rows = db.execute(
        "SELECT equity_usd, liquidated FROM equity_snapshots "
        "WHERE student_id = ? ORDER BY ts ASC",
        [student_id],
    )
    return [r["equity_usd"] for r in rows], [r["liquidated"] for r in rows]


def upsert_score(db: Turso, student_id: str, ts: int, sc: Score, now_ms: int) -> None:
    db.execute(
        """
        INSERT INTO scores (student_id, ts, equity_usd, start_equity_usd,
                            total_return, max_drawdown, risk_adjusted,
                            blew_up, n_snapshots, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(student_id) DO UPDATE SET
            ts=excluded.ts, equity_usd=excluded.equity_usd,
            start_equity_usd=excluded.start_equity_usd,
            total_return=excluded.total_return, max_drawdown=excluded.max_drawdown,
            risk_adjusted=excluded.risk_adjusted, blew_up=excluded.blew_up,
            n_snapshots=excluded.n_snapshots, updated_at=excluded.updated_at
        """,
        [student_id, ts, sc.last_equity_usd, sc.start_equity_usd, sc.total_return,
         sc.max_drawdown, sc.risk_adjusted, int(sc.blew_up), sc.n, now_ms],
    )


# ===========================================================================
# Main poll loop
# ===========================================================================
def poll_once() -> int:
    """One full pass over the roster. Returns the number of students polled OK."""
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        print("ERROR: set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN.", file=sys.stderr)
        return 0
    if httpx is None:
        print("ERROR: httpx is required for live polling (uv run --with httpx).", file=sys.stderr)
        return 0

    roster = load_roster()
    if not roster:
        print("No roster found (set ROSTER_JSON or roster.json). Nothing to poll.")
        return 0

    db = Turso(url, token)
    dex = Deribit()
    now_ms = int(time.time() * 1000)
    ok = 0
    failed = 0

    try:
        # The BTC index is shared by every student (USD conversion). If even this
        # public read fails the run can't price anything, so bail cleanly.
        try:
            index = dex.index_price("BTC")
        except Exception as exc:
            print(f"ERROR: could not fetch BTC index, aborting poll: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 0
        print(f"BTC index = {index:,.2f} USD")

        for s in roster:
            # Each student is fully isolated: a bad/expired/auth-failing key, a
            # network blip, or a Turso hiccup for ONE student is logged and
            # skipped — it must never abort the poll for everyone else.
            try:
                upsert_student(db, s, now_ms)
                if not (s.client_id and s.client_secret):
                    print(f"  - {s.id}: no key yet, skipping balance fetch")
                    continue

                # Auth + balance read are the parts most likely to fail (revoked
                # key, wrong scope, testnet down). Keep them in the guarded block.
                tok = dex.auth(s.client_id, s.client_secret)
                summary = dex.account_summary(tok, "BTC")
                equity_btc = float(summary.get("equity", 0.0))
                equity_usd = equity_btc * index
                liquidated = equity_btc <= 0.0

                insert_snapshot(db, s.id, now_ms, equity_usd, equity_btc, index, liquidated)
                hist_equity, hist_liq = read_history(db, s.id)
                sc = compute_score(hist_equity, hist_liq, s.start_equity_usd)
                upsert_score(db, s.id, now_ms, sc, now_ms)

                flag = " 💀 BLEW UP" if sc.blew_up else ""
                print(f"  - {s.id}: equity ${equity_usd:,.0f} "
                      f"ret {sc.total_return:+.1%} dd {sc.max_drawdown:.1%} "
                      f"RA {sc.risk_adjusted:+.2f}{flag}")
                ok += 1
            except Exception as exc:  # one bad key shouldn't sink the whole run
                failed += 1
                print(f"  - {s.id}: SKIPPED ({type(exc).__name__}: {exc})",
                      file=sys.stderr)
                continue
    finally:
        dex.close()
        db.close()

    print(f"Polled {ok}/{len(roster)} students OK ({failed} skipped).")
    return ok


def self_test() -> None:
    """Offline check of the scoring math — no network, no DB. Used in CI."""
    # A survivor that grinds up: positive return, tiny drawdown -> high RA.
    s1 = compute_score([100, 102, 101, 105, 110])
    assert s1.blew_up is False
    assert s1.risk_adjusted > 0
    # A blow-up: drops below 25% of the $100 baseline -> blew_up True.
    s2 = compute_score([100, 80, 40, 20, 5])
    assert s2.blew_up is True
    # Liquidation flag forces blew_up even if equity looks fine.
    s3 = compute_score([100, 100, 100], [0, 0, 1])
    assert s3.blew_up is True
    # Drawdown floor protects against divide-by-zero / absurd RA.
    s4 = compute_score([100, 100, 100])
    assert s4.max_drawdown == 0.0 and s4.risk_adjusted == 0.0
    # Survivor beats blow-up on the ranking metric, all else equal.
    assert s1.risk_adjusted > s2.risk_adjusted
    print("self-test OK: scoring matches score.py contract "
          "(risk_adjusted = total_return / max(max_drawdown, 0.02), "
          "blew_up = liquidated OR equity < 25% of start).")


def main() -> int:
    ap = argparse.ArgumentParser(description="Leaderboard poller")
    ap.add_argument("--self-test", action="store_true",
                    help="run the offline scoring sanity check and exit")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0
    return 0 if poll_once() >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
