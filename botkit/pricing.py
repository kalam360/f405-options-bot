"""Pure option-pricing math: Black-Scholes price, implied vol, Greeks.

No I/O. `d1d2` and `bs_price` vectorize over NumPy arrays of S, K, T, sigma;
`greeks`, `fd_greeks`, and `implied_vol` are scalar (they return plain floats).
Every function is unit-tested.
This is the small, tested library a real desk keeps and reuses.
"""
from __future__ import annotations
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq


def d1d2(S, K, T, sigma, r=0.0):
    """The two standard Black-Scholes terms. Returns (d1, d2)."""
    S, K, T, sigma = map(np.asarray, (S, K, T, sigma))
    vol_t = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / vol_t
    d2 = d1 - vol_t
    return d1, d2


def bs_price(S, K, T, sigma, r=0.0, kind="C"):
    """Black-Scholes price of a European option. kind='C' call, 'P' put.

    Degenerate scalar inputs (T<=0 or sigma<=0) return the deterministic
    intrinsic value instead of a NaN, so the function is total."""
    if np.ndim(S) == np.ndim(K) == np.ndim(T) == np.ndim(sigma) == 0 and (T <= 0 or sigma <= 0):
        disc = np.exp(-r * T) if T > 0 else 1.0
        intrinsic = (S - K * disc) if kind == "C" else (K * disc - S)
        return float(max(0.0, intrinsic))
    d1, d2 = d1d2(S, K, T, sigma, r)
    disc = np.exp(-r * T)
    if kind == "C":
        return S * norm.cdf(d1) - K * disc * norm.cdf(d2)
    return K * disc * norm.cdf(-d2) - S * norm.cdf(-d1)


def greeks(S, K, T, sigma, r=0.0, kind="C"):
    """Analytic Greeks. delta/gamma/vega/theta/rho.

    vega is per 1.00 change in vol (divide by 100 for 'per 1 vol point').
    theta is per year (divide by 365 for 'per calendar day').

    Degenerate scalar inputs (T<=0 or sigma<=0) return deterministic limits
    (delta = in/out-of-money indicator; gamma/vega/theta = 0) instead of NaN.
    """
    if np.ndim(S) == np.ndim(K) == np.ndim(T) == np.ndim(sigma) == 0 and (T <= 0 or sigma <= 0):
        disc = np.exp(-r * T) if T > 0 else 1.0
        in_money = (S > K * disc) if kind == "C" else (S < K * disc)
        delta = (1.0 if kind == "C" else -1.0) if in_money else 0.0
        return {"delta": delta, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}
    d1, d2 = d1d2(S, K, T, sigma, r)
    disc = np.exp(-r * T)
    pdf = norm.pdf(d1)
    gamma = pdf / (S * sigma * np.sqrt(T))
    vega = S * pdf * np.sqrt(T)
    if kind == "C":
        delta = norm.cdf(d1)
        theta = -S * pdf * sigma / (2 * np.sqrt(T)) - r * K * disc * norm.cdf(d2)
        rho = K * T * disc * norm.cdf(d2)
    else:
        delta = norm.cdf(d1) - 1.0
        theta = -S * pdf * sigma / (2 * np.sqrt(T)) + r * K * disc * norm.cdf(-d2)
        rho = -K * T * disc * norm.cdf(-d2)
    return {"delta": float(delta), "gamma": float(gamma), "vega": float(vega),
            "theta": float(theta), "rho": float(rho)}


def fd_greeks(S, K, T, sigma, r=0.0, kind="C", h_rel=1e-3, h_vol=1e-4):
    """Greeks by bumping inputs and re-pricing (no calculus).

    Convention-independent proof that the analytic Greeks are right.
    gamma is a 2nd derivative, so h_rel is chosen larger than a naive 1e-6
    to keep round-off from dominating; h_rel=1e-3 gives gamma rel err ~2.7e-6.
    """
    h = S * h_rel
    p_up = bs_price(S + h, K, T, sigma, r, kind)
    p_dn = bs_price(S - h, K, T, sigma, r, kind)
    p_0 = bs_price(S, K, T, sigma, r, kind)
    delta = (p_up - p_dn) / (2 * h)
    gamma = (p_up - 2 * p_0 + p_dn) / (h * h)
    v_up = bs_price(S, K, T, sigma + h_vol, r, kind)
    v_dn = bs_price(S, K, T, sigma - h_vol, r, kind)
    vega = (v_up - v_dn) / (2 * h_vol)
    return {"delta": float(delta), "gamma": float(gamma), "vega": float(vega)}


def implied_vol(price, S, K, T, r=0.0, kind="C", lo=1e-4, hi=5.0):
    """Recover the volatility implied by a market price (Brentq root-find).

    Returns np.nan when no solution exists in [lo, hi] (e.g. price below
    intrinsic, near-zero T, or a crossed/garbage quote).
    """
    if T <= 0 or price <= 0:
        return np.nan
    disc_k = K * np.exp(-r * T)
    intrinsic = max(0.0, (S - disc_k) if kind == "C" else (disc_k - S))
    if price < intrinsic - 1e-8:
        return np.nan
    def f(sig):
        return bs_price(S, K, T, sig, r, kind) - price
    try:
        if f(lo) * f(hi) > 0:
            return np.nan
        return float(brentq(f, lo, hi, xtol=1e-8, maxiter=100))
    except (ValueError, RuntimeError):
        return np.nan


def implied_vol_newton(price, S, K, T, r=0.0, kind="C", guess=0.5, iters=50):
    """OPTIONAL ASIDE (shown in the notebook, not on the main path): a faster
    but more fragile Newton iteration using vega. Brentq above is the engine."""
    sig = guess
    for _ in range(iters):
        diff = bs_price(S, K, T, sig, r, kind) - price
        v = greeks(S, K, T, sig, r, kind)["vega"]
        if v < 1e-8:
            break
        step = diff / v
        sig -= step
        if abs(step) < 1e-8:
            break
    return float(sig) if 0 < sig < 5 else np.nan
