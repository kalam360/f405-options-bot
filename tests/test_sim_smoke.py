"""Smoke test: the runner produces a complete journal in sim mode, offline.

We run the provided `strategies.template` (a safe do-nothing stub) through the
real runner in `sim` mode and assert it leaves a well-formed journal behind. No
keys, no network — exactly what CI and the autograder rely on.
"""
import csv
import os

import pytest

from botkit.config import Config
from botkit.journal import EQUITY_HEADER, TRADES_HEADER
from botkit.runner import run
from strategies.template import MyStrategy, MyRisk

# Repo root (so the default sim_snapshot path resolves regardless of cwd).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sim_config(journal_dir: str) -> Config:
    cfg = Config()  # defaults: mode="sim", seeded offline replay
    cfg.mode = "sim"
    cfg.journal_dir = journal_dir
    cfg.sim_snapshot = os.path.join(REPO_ROOT, "data", "deribit_snapshot.json")
    cfg.sim_days = 3.0  # keep the smoke test quick
    return cfg


def test_sim_run_writes_journal(tmp_path):
    cfg = _sim_config(str(tmp_path))
    summary = run(cfg, MyStrategy(), MyRisk())

    # Runner returned a sane summary.
    assert summary["mode"] == "sim"
    assert summary["ticks"] > 0

    equity_path = tmp_path / "equity.csv"
    trades_path = tmp_path / "trades.csv"
    meta_path = tmp_path / "meta.json"
    assert equity_path.exists() and trades_path.exists() and meta_path.exists()

    # equity.csv: fixed header + one row per tick.
    with open(equity_path, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == EQUITY_HEADER
    assert len(rows) - 1 == summary["ticks"] > 1

    # trades.csv: at least the fixed header (stub places no trades).
    with open(trades_path, newline="") as f:
        trade_rows = list(csv.reader(f))
    assert trade_rows[0] == TRADES_HEADER


def test_sim_is_deterministic(tmp_path):
    """Same seed -> byte-identical equity curve (sim must be reproducible)."""
    a, b = tmp_path / "a", tmp_path / "b"
    run(_sim_config(str(a)), MyStrategy(), MyRisk())
    run(_sim_config(str(b)), MyStrategy(), MyRisk())
    assert (a / "equity.csv").read_text() == (b / "equity.csv").read_text()
