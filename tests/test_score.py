"""Tests for score.py against committed fixture journals.

Two synthetic equity curves live under tests/fixtures/:
  * healthy/  — a delta-hedged vol seller: steady gains, tiny drawdowns, survives.
  * blowup/   — a naive short straddle: theta for a few days, then liquidation.

The grader's whole job hinges on telling these two apart, so we assert the key
metrics and the rubric mapping for each, plus that score.json is written.
"""
import json
import os
import shutil

import pytest

import score

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def test_healthy_run_scores_well():
    s = score.score_run(os.path.join(FIX, "healthy"))
    assert s.blew_up is False
    assert s.total_return > 0.0
    assert 0.0 <= s.max_drawdown < 0.25          # a survivor's drawdown is bounded
    assert s.risk_adjusted > 0.0
    assert s.score_0_3 >= 2.0                     # at/above the baseline-to-beat
    assert s.score_0_3 <= 3.0
    # 15 days hourly -> at least two weekly cycles bucketed.
    assert len(s.cycles) >= 2


def test_blowup_run_scores_zero():
    s = score.score_run(os.path.join(FIX, "blowup"))
    assert s.blew_up is True                      # liquidated flag + equity < 25%
    assert s.score_0_3 == 0.0                     # a blow-up is an automatic 0
    assert s.max_drawdown > 0.5                   # catastrophic peak-to-trough fall


def test_blowup_detected_by_equity_floor_alone(tmp_path):
    """blew_up must trip on the 25%-of-start floor even if the liquidated flag
    was never set (a strategy can bleed out without a formal liquidation)."""
    src = os.path.join(FIX, "blowup", "equity.csv")
    dst_dir = tmp_path / "no_flag"
    dst_dir.mkdir()
    # Copy the blow-up curve but force the liquidated flag column to 0 everywhere.
    lines = open(src).read().splitlines()
    header = lines[0]
    out = [header]
    for ln in lines[1:]:
        cols = ln.split(",")
        cols[-1] = "0"
        out.append(",".join(cols))
    (dst_dir / "equity.csv").write_text("\n".join(out) + "\n")

    s = score.score_run(str(dst_dir))
    assert s.blew_up is True
    assert s.score_0_3 == 0.0


def test_risk_adjusted_uses_drawdown_floor():
    """risk_adjusted divides by max(max_drawdown, 0.02): a nearly flat-but-up
    curve can't post an infinite ratio."""
    assert score.MIN_DRAWDOWN_FLOOR == 0.02
    s = score.score_run(os.path.join(FIX, "healthy"))
    # s.* fields are each rounded to 6dp, so allow a small recompute tolerance.
    expected = s.total_return / max(s.max_drawdown, score.MIN_DRAWDOWN_FLOOR)
    assert s.risk_adjusted == pytest.approx(expected, rel=1e-3)


def test_score_json_written(tmp_path):
    """`main` writes a valid score.json into the run dir."""
    run_dir = tmp_path / "healthy"
    shutil.copytree(os.path.join(FIX, "healthy"), run_dir)
    rc = score.main([str(run_dir)])
    assert rc == 0
    out = run_dir / "score.json"
    assert out.exists()
    data = json.loads(out.read_text())
    for key in ("total_return", "max_drawdown", "sharpe", "risk_adjusted",
                "blew_up", "cycles", "score_0_3"):
        assert key in data


def test_score_0_3_mapping_anchors():
    """The documented anchors hold: blow-up -> 0; baseline -> 2; top -> 3."""
    assert score._score_0_3(5.0, blew_up=True) == 0.0
    assert score._score_0_3(score.BASELINE_RISK_ADJUSTED, blew_up=False) == pytest.approx(2.0)
    assert score._score_0_3(score.TOP_RISK_ADJUSTED, blew_up=False) == pytest.approx(3.0)
    assert score._score_0_3(10.0, blew_up=False) == 3.0      # capped
    assert score._score_0_3(-1.0, blew_up=False) >= 0.5      # survivor floor
