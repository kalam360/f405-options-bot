"""Pricing sanity checks for botkit.pricing.

These are the small, fast invariants a desk relies on: an ATM anchor for the
Black-Scholes price, put-call parity, and the sign/textbook value of each Greek.
If any of these break, every downstream number (marks, Greeks, the journal,
the score) is silently wrong.
"""
import math

import pytest

from botkit.pricing import bs_price, greeks, fd_greeks, implied_vol


# A representative weekly-option setup: ~$60k BTC, 7 days, 65% vol.
S, K, T, SIGMA = 60_000.0, 60_000.0, 7.0 / 365.0, 0.65


def test_bs_price_atm_anchor():
    """For an ATM option (S==K, r=0) BS price ~= 0.4 * S * sigma * sqrt(T).

    This Brenner-Subrahmanyam approximation is accurate to well under 1% ATM, so
    it pins the absolute price level, not just the sign.
    """
    approx = 0.4 * S * SIGMA * math.sqrt(T)
    call = bs_price(S, K, T, SIGMA, kind="C")
    assert call == pytest.approx(approx, rel=0.02)
    # ATM call and put are equal when r=0 (parity with S==K).
    put = bs_price(S, K, T, SIGMA, kind="P")
    assert call == pytest.approx(put, abs=1e-6)


def test_put_call_parity():
    """C - P == S - K*exp(-rT). With r=0 that is just S - K, at any strike."""
    for k in (50_000.0, 60_000.0, 72_000.0):
        c = bs_price(S, k, T, SIGMA, kind="C")
        p = bs_price(S, k, T, SIGMA, kind="P")
        assert (c - p) == pytest.approx(S - k, abs=1e-6)


def test_greeks_signs_and_values():
    """Call delta in (0,1), put delta in (-1,0); gamma/vega > 0; theta < 0."""
    gc = greeks(S, K, T, SIGMA, kind="C")
    gp = greeks(S, K, T, SIGMA, kind="P")

    assert 0.0 < gc["delta"] < 1.0
    assert -1.0 < gp["delta"] < 0.0
    # ATM call delta ~ 0.5 (a touch above with positive carry-free drift).
    assert gc["delta"] == pytest.approx(0.5, abs=0.06)
    # Call/put deltas differ by exactly 1 (r=0).
    assert (gc["delta"] - gp["delta"]) == pytest.approx(1.0, abs=1e-6)

    for g in (gc, gp):
        assert g["gamma"] > 0.0
        assert g["vega"] > 0.0
        assert g["theta"] < 0.0   # long options bleed time value


def test_analytic_greeks_match_finite_difference():
    """The tested analytic Greeks agree with a bump-and-reprice estimate."""
    g = greeks(S, K, T, SIGMA, kind="C")
    fd = fd_greeks(S, K, T, SIGMA, kind="C")
    assert g["delta"] == pytest.approx(fd["delta"], rel=1e-4)
    assert g["vega"] == pytest.approx(fd["vega"], rel=1e-4)
    assert g["gamma"] == pytest.approx(fd["gamma"], rel=1e-3)


def test_implied_vol_roundtrip():
    """Pricing at a known vol then inverting recovers that vol."""
    price = bs_price(S, K, T, SIGMA, kind="C")
    iv = implied_vol(price, S, K, T, kind="C")
    assert iv == pytest.approx(SIGMA, abs=1e-4)
