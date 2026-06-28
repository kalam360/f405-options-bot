"""Seed the leaderboard with synthetic demo students.

Before any real student registers a read-only Deribit key, the leaderboard would
be empty — not a great first impression for a demo or a dry-run. This script
inserts three *synthetic* students with a few days of equity history so the web
app has something to render: a ranking, sparklines, and a 💀 blow-up badge.

The three demo students are deliberately chosen to tell the course's story:

  * demo-steady-eddie  — grinds capital up with a tiny drawdown. LOW raw return,
                         but the highest **risk-adjusted** score. The one to copy.
  * demo-yolo-yolanda  — bigger raw return, but a stomach-churning drawdown along
                         the way, so a LOWER risk-adjusted score than steady-eddie.
                         Shows why we divide return by drawdown.
  * demo-naked-nick    — the naked short straddle: prints theta for days, then a
                         weekly-expiry jump liquidates the account. blew_up = True.

It reuses poll.py's Turso client and scoring (`compute_score`) so the demo rows
are scored by exactly the same math as live rows.

Idempotent & safe: every demo row uses a `demo-` id prefix and is DELETED before
re-inserting, so you can run this as many times as you like without duplicating.
It only ever touches `demo-*` rows — real students are never affected.

Run it:
    export TURSO_DATABASE_URL=libsql://...
    export TURSO_AUTH_TOKEN=...
    uv run --with httpx python leaderboard/poller/seed_demo.py
"""
from __future__ import annotations

import os
import sys
import time

# Reuse the poller's Turso HTTP client and the *identical* scoring math, so the
# seeded rows are indistinguishable in shape/score from rows the live poller writes.
from poll import Turso, Student, compute_score, upsert_student, insert_snapshot, upsert_score

DEMO_PREFIX = "demo-"
DEMO_INDEX_USD = 60_000.0  # fixed BTC index for the synthetic USD<->BTC convert
START_EQUITY_USD = 100_000.0
SNAPSHOT_INTERVAL_MS = 6 * 60 * 60 * 1000  # one snapshot every 6 hours


# ---------------------------------------------------------------------------
# The three synthetic equity paths (oldest -> newest), in USD.
# Hand-built so steady-eddie out-ranks yolo-yolanda on risk-adjusted return even
# though yolanda's raw return is higher, and naked-nick clearly blows up.
# ---------------------------------------------------------------------------
def _steady_eddie_path() -> list[float]:
    # Slow, almost-monotonic grind: ~+8% with a max drawdown of ~1%.
    return [
        100_000, 100_400, 100_200, 101_100, 101_600, 101_400, 102_300, 103_000,
        102_800, 103_700, 104_500, 104_300, 105_200, 106_000, 106_400, 107_100,
        106_900, 107_600, 108_200, 108_000,
    ]


def _yolo_yolanda_path() -> list[float]:
    # Higher headline return (~+14%) but a brutal ~18% peak-to-trough drawdown
    # mid-run -> worse risk-adjusted score than the steady grind above.
    return [
        100_000, 104_000, 108_000, 112_000, 109_000, 99_000, 92_000, 96_000,
        103_000, 110_000, 113_000, 116_000, 112_000, 118_000, 121_000, 117_000,
        119_000, 122_000, 113_000, 114_000,
    ]


def _naked_nick_path() -> list[float]:
    # The naked short straddle: harvests theta and looks great (peaks ~+9%), then
    # a single weekly-expiry jump through the short strike liquidates it.
    return [
        100_000, 101_500, 102_800, 103_500, 104_900, 105_800, 106_500, 107_900,
        108_600, 109_100, 108_400, 95_000, 71_000, 44_000, 19_000, 4_000,
    ]


DEMO_STUDENTS: list[tuple[Student, list[float], bool]] = [
    # (roster metadata, equity path USD, did_liquidate)
    (
        Student(
            id=f"{DEMO_PREFIX}steady-eddie", name="Steady Eddie (demo)",
            client_id="", client_secret="", github="demo", team="Demo",
            start_equity_usd=START_EQUITY_USD,
        ),
        _steady_eddie_path(),
        False,
    ),
    (
        Student(
            id=f"{DEMO_PREFIX}yolo-yolanda", name="YOLO Yolanda (demo)",
            client_id="", client_secret="", github="demo", team="Demo",
            start_equity_usd=START_EQUITY_USD,
        ),
        _yolo_yolanda_path(),
        False,
    ),
    (
        Student(
            id=f"{DEMO_PREFIX}naked-nick", name="Naked Nick (demo)",
            client_id="", client_secret="", github="demo", team="Demo",
            start_equity_usd=START_EQUITY_USD,
        ),
        _naked_nick_path(),
        True,  # the account gets liquidated on the final snapshot
    ),
]


def clear_demo_rows(db: Turso) -> None:
    """Delete every `demo-*` row so re-running is idempotent.

    Children (scores, equity_snapshots) are deleted before the parent (students)
    to respect the foreign-key references in schema.sql.
    """
    db.execute("DELETE FROM scores WHERE student_id LIKE ?", [f"{DEMO_PREFIX}%"])
    db.execute("DELETE FROM equity_snapshots WHERE student_id LIKE ?", [f"{DEMO_PREFIX}%"])
    db.execute("DELETE FROM students WHERE id LIKE ?", [f"{DEMO_PREFIX}%"])


def seed_student(db: Turso, student: Student, path: list[float],
                 did_liquidate: bool, now_ms: int) -> None:
    """Insert one demo student: roster row + equity history + final score."""
    upsert_student(db, student, now_ms)

    n = len(path)
    # Lay the snapshots out backwards from "now" so the newest is the latest poll.
    base_ts = now_ms - (n - 1) * SNAPSHOT_INTERVAL_MS
    liq_flags: list[int] = []
    for i, equity_usd in enumerate(path):
        ts = base_ts + i * SNAPSHOT_INTERVAL_MS
        # liquidation flag only on the final snapshot, and only if it blew up
        liquidated = did_liquidate and (i == n - 1)
        liq_flags.append(int(liquidated))
        equity_btc = equity_usd / DEMO_INDEX_USD
        insert_snapshot(db, student.id, ts, equity_usd, equity_btc,
                        DEMO_INDEX_USD, liquidated)

    # Score from the full series with the SAME function the live poller uses.
    sc = compute_score(path, liq_flags, student.start_equity_usd)
    last_ts = base_ts + (n - 1) * SNAPSHOT_INTERVAL_MS
    upsert_score(db, student.id, last_ts, sc, now_ms)

    flag = " 💀 BLEW UP" if sc.blew_up else ""
    print(f"  - {student.id}: {n} snapshots, ret {sc.total_return:+.1%} "
          f"dd {sc.max_drawdown:.1%} RA {sc.risk_adjusted:+.2f}{flag}")


def main() -> int:
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        print("ERROR: set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN.", file=sys.stderr)
        return 1

    db = Turso(url, token)
    now_ms = int(time.time() * 1000)
    try:
        print("Clearing existing demo rows (demo-*) ...")
        clear_demo_rows(db)
        print("Seeding demo students ...")
        for student, path, did_liquidate in DEMO_STUDENTS:
            seed_student(db, student, path, did_liquidate, now_ms)
    finally:
        db.close()

    print(f"Seeded {len(DEMO_STUDENTS)} demo students. "
          "Re-run any time — it clears demo-* first, so it is idempotent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
