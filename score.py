"""score.py — turn a run's journal into a deterministic, risk-adjusted grade.

Usage:
    uv run python score.py runs/latest        # prints a table, writes score.json

It reads ONLY the fixed-schema `equity.csv` written by `botkit.journal` (one row
per tick) and computes the rubric's "performance" metrics:

  * total_return    — end equity / start equity - 1
  * max_drawdown    — worst peak-to-trough fall in equity (a positive fraction)
  * sharpe          — per-tick return mean/std, annualised by ticks-per-year
  * risk_adjusted   — total_return / max(max_drawdown, 0.02)   (the headline number)
  * blew_up         — liquidated flag ever set, OR equity ever < 25% of start
  * cycles          — P&L bucketed into weekly (7-day) cycles, Fri->Fri in spirit
  * score_0_3       — rubric line 1 (performance), 0..3, documented mapping below

Everything is deterministic and offline: pandas + the standard library only. No
network, no randomness, no wall-clock. The same equity.csv always scores the same.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# score_0_3 mapping — rubric line 1 (risk-adjusted performance), documented.
#
# The grade is anchored to the *delta-hedged vol-seller baseline* (the strategy
# students are told to beat). We express that anchor as a target `risk_adjusted`
# value so scoring stays self-contained and deterministic (no need to re-run the
# baseline at grading time). Tune these two constants if the baseline's measured
# risk_adjusted drifts — they are the only knobs.
#
#   blew_up                              -> 0.0   (liquidated or lost >75%: an F)
#   survived but no edge (ra <= 0)       -> 1.0   (alive, but didn't make money)
#   ra == BASELINE_RISK_ADJUSTED         -> 2.0   (matched the baseline-to-beat)
#   ra >= TOP_RISK_ADJUSTED              -> 3.0   (clearly best-in-class, capped)
#
# Between the anchors the score is linearly interpolated; survivors are floored
# at 0.5 (surviving is always worth more than blowing up).
# ---------------------------------------------------------------------------
BASELINE_RISK_ADJUSTED = 1.0   # delta-hedged baseline's expected total_return/drawdown
TOP_RISK_ADJUSTED = 3.0        # a great run; risk_adjusted at/above this caps the score
BLOWUP_EQUITY_FRACTION = 0.25  # equity ever below this fraction of start == blew up
MIN_DRAWDOWN_FLOOR = 0.02      # risk_adjusted denominator floor (CONTRACT)
MS_PER_YEAR = 365.0 * 24.0 * 3600.0 * 1000.0
MS_PER_WEEK = 7.0 * 24.0 * 3600.0 * 1000.0


@dataclass
class Cycle:
    """P&L for one weekly trading cycle (a 7-day bucket from the run start)."""
    cycle: int
    start_iso: str
    end_iso: str
    ticks: int
    start_equity_usd: float
    end_equity_usd: float
    pnl_usd: float
    return_pct: float


@dataclass
class Score:
    """The full, JSON-serialisable scorecard for one run."""
    journal_dir: str
    ticks: int
    start_equity_usd: float
    end_equity_usd: float
    total_return: float
    max_drawdown: float
    sharpe: float
    risk_adjusted: float
    blew_up: bool
    ticks_per_year: float
    cycles: list  # list[dict] (Cycle rows)
    score_0_3: float


# ---------------------------------------------------------------------------
# metric helpers (each pure, each easy to unit-test)
# ---------------------------------------------------------------------------
def _max_drawdown(equity: pd.Series) -> float:
    """Largest peak-to-trough drop as a positive fraction (0.30 == down 30%)."""
    running_peak = equity.cummax()
    drawdown = (equity - running_peak) / running_peak
    worst = drawdown.min()
    return float(-worst) if worst < 0 else 0.0


def _sharpe(equity: pd.Series, ticks_per_year: float) -> float:
    """Annualised Sharpe of per-tick simple returns (risk-free = 0).

    Returns 0.0 when there is no variation (e.g. a flat or single-point series),
    so the number is always finite and deterministic.
    """
    rets = equity.pct_change().dropna()
    if len(rets) < 2:
        return 0.0
    std = rets.std(ddof=1)
    if std == 0 or pd.isna(std):
        return 0.0
    return float(rets.mean() / std * (ticks_per_year ** 0.5))


def _ticks_per_year(ts: pd.Series) -> float:
    """Infer ticks/year from the median spacing between snapshot timestamps."""
    if len(ts) < 2:
        return 0.0
    dt_ms = ts.diff().dropna().median()
    if not dt_ms or dt_ms <= 0:
        return 0.0
    return float(MS_PER_YEAR / dt_ms)


def _cycles(df: pd.DataFrame) -> list[Cycle]:
    """Bucket the run into consecutive 7-day cycles and measure P&L per cycle."""
    start_ts = int(df["ts"].iloc[0])
    bucket = ((df["ts"] - start_ts) // MS_PER_WEEK).astype(int)
    out: list[Cycle] = []
    for cyc, grp in df.groupby(bucket):
        e0 = float(grp["equity_usd"].iloc[0])
        e1 = float(grp["equity_usd"].iloc[-1])
        out.append(Cycle(
            cycle=int(cyc),
            start_iso=str(grp["iso"].iloc[0]),
            end_iso=str(grp["iso"].iloc[-1]),
            ticks=int(len(grp)),
            start_equity_usd=round(e0, 2),
            end_equity_usd=round(e1, 2),
            pnl_usd=round(e1 - e0, 2),
            return_pct=round((e1 / e0 - 1.0) if e0 else 0.0, 6),
        ))
    return out


def _score_0_3(risk_adjusted: float, blew_up: bool) -> float:
    """Map risk_adjusted -> 0..3 using the anchors documented at module top."""
    if blew_up:
        return 0.0
    # Piecewise-linear interpolation across (ra, score) anchors.
    anchors = [
        (0.0, 1.0),                              # survived, no edge
        (BASELINE_RISK_ADJUSTED, 2.0),           # matched the baseline
        (TOP_RISK_ADJUSTED, 3.0),                # best-in-class
    ]
    ra = risk_adjusted
    if ra <= anchors[0][0]:
        score = anchors[0][1]
    elif ra >= anchors[-1][0]:
        score = anchors[-1][1]
    else:
        score = anchors[0][1]
        for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
            if x0 <= ra <= x1:
                frac = (ra - x0) / (x1 - x0) if x1 > x0 else 0.0
                score = y0 + frac * (y1 - y0)
                break
    # Survivors are always worth at least 0.5; only a blow-up scores 0.
    return round(max(0.5, score), 3)


# ---------------------------------------------------------------------------
# top-level scoring
# ---------------------------------------------------------------------------
def score_run(journal_dir: str) -> Score:
    """Read `<journal_dir>/equity.csv` and compute the full scorecard."""
    equity_path = os.path.join(journal_dir, "equity.csv")
    if not os.path.exists(equity_path):
        raise FileNotFoundError(f"no equity.csv in {journal_dir!r}")

    df = pd.read_csv(equity_path)
    if df.empty:
        raise ValueError(f"equity.csv in {journal_dir!r} has no rows")

    equity = df["equity_usd"].astype(float)
    start_equity = float(equity.iloc[0])
    end_equity = float(equity.iloc[-1])

    total_return = (end_equity / start_equity - 1.0) if start_equity else 0.0
    max_dd = _max_drawdown(equity)
    ticks_per_year = _ticks_per_year(df["ts"].astype(float))
    sharpe = _sharpe(equity, ticks_per_year)
    risk_adjusted = total_return / max(max_dd, MIN_DRAWDOWN_FLOOR)

    liquidated_ever = bool(df["liquidated"].astype(int).max() > 0) if "liquidated" in df else False
    below_floor = bool((equity < BLOWUP_EQUITY_FRACTION * start_equity).any())
    blew_up = liquidated_ever or below_floor

    cycles = _cycles(df)
    score_0_3 = _score_0_3(risk_adjusted, blew_up)

    return Score(
        journal_dir=journal_dir,
        ticks=int(len(df)),
        start_equity_usd=round(start_equity, 2),
        end_equity_usd=round(end_equity, 2),
        total_return=round(total_return, 6),
        max_drawdown=round(max_dd, 6),
        sharpe=round(sharpe, 4),
        risk_adjusted=round(risk_adjusted, 6),
        blew_up=blew_up,
        ticks_per_year=round(ticks_per_year, 2),
        cycles=[asdict(c) for c in cycles],
        score_0_3=score_0_3,
    )


def _format_table(s: Score) -> str:
    """Human-readable summary printed to stdout."""
    lines = [
        f"Scorecard for {s.journal_dir}",
        "-" * 48,
        f"  ticks                {s.ticks}",
        f"  start equity (USD)   {s.start_equity_usd:,.2f}",
        f"  end equity (USD)     {s.end_equity_usd:,.2f}",
        f"  total_return         {s.total_return:+.2%}",
        f"  max_drawdown         {s.max_drawdown:.2%}",
        f"  sharpe (annualised)  {s.sharpe:+.2f}",
        f"  risk_adjusted        {s.risk_adjusted:+.3f}",
        f"  blew_up              {'YES (skull)' if s.blew_up else 'no'}",
        "-" * 48,
        "  weekly cycles:",
    ]
    for c in s.cycles:
        lines.append(
            f"    cycle {c['cycle']}: P&L {c['pnl_usd']:+,.2f} USD "
            f"({c['return_pct']:+.2%}, {c['ticks']} ticks)"
        )
    lines += [
        "-" * 48,
        f"  SCORE (0-3)          {s.score_0_3}",
    ]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Score a run's journal (risk-adjusted).")
    ap.add_argument("run_dir", nargs="?", default="runs/latest",
                    help="run directory containing equity.csv (default: runs/latest)")
    args = ap.parse_args(argv)

    s = score_run(args.run_dir)
    print(_format_table(s))

    out_path = os.path.join(args.run_dir, "score.json")
    with open(out_path, "w") as f:
        json.dump(asdict(s), f, indent=2)
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
