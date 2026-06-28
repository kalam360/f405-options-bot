"""Market feeds: where the chain comes from each tick.

Two implementations behind one tiny interface (`MarketFeed.chains()` yields one
`Chain` per tick):

* `LiveFeed`  — polls Deribit testnet for the front-weekly expiry every
  `tick_seconds`. Used in `live` mode.
* `ReplayFeed` — fully OFFLINE and DETERMINISTIC. It loads a captured snapshot
  (`data/deribit_snapshot.json`), picks the expiry nearest to 7 days as "the
  weekly", then synthesises a `sim_days`-long path: the BTC index follows a
  seeded geometric Brownian motion, and every option is re-marked from its
  captured `mark_iv` with `pricing.bs_price` on that expiry's forward. Same seed
  -> same run, with no network and no keys. This is what makes the assignment
  testable in CI and reproducible for graders.
"""
from __future__ import annotations
import json
import math
import time
from typing import Iterator, Protocol, runtime_checkable

import numpy as np

from . import pricing
from .config import Config
from .types import Chain, OptionQuote


@runtime_checkable
class MarketFeed(Protocol):
    """Anything the runner can pull chains from."""
    def chains(self) -> Iterator[Chain]:
        ...


# ---------------------------------------------------------------------------
# Live feed
# ---------------------------------------------------------------------------
class LiveFeed:
    """Polls the front-weekly expiry from Deribit testnet every `tick_seconds`."""

    def __init__(self, client, cfg: Config) -> None:
        self.client = client
        self.cfg = cfg

    def _front_weekly_expiry(self) -> int:
        """The active expiry whose days-to-expiry is closest to 7."""
        instruments = self.client.get_instruments(self.cfg.currency, "option")
        now_ms = time.time() * 1000
        expiries = sorted({int(i["expiration_timestamp"]) for i in instruments})
        # only future expiries
        future = [e for e in expiries if e > now_ms]
        target_days = 7.0
        return min(future, key=lambda e: abs((e - now_ms) / 1000 / 86400 - target_days))

    def chains(self) -> Iterator[Chain]:
        # Re-evaluate the front-weekly each tick so we roll to the next expiry.
        while True:
            expiry = self._front_weekly_expiry()
            yield self.client.get_chain(expiry, self.cfg.currency)
            time.sleep(self.cfg.tick_seconds)


# ---------------------------------------------------------------------------
# Replay feed (offline, deterministic)
# ---------------------------------------------------------------------------
class ReplayFeed:
    """Offline synthetic feed driven by a captured snapshot + seeded GBM."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        snap = json.load(open(cfg.sim_snapshot))
        self.captured_iso = snap.get("captured_at", "")
        self.index0 = float(snap["index"]["index_price"])

        # Index instruments + tickers by name.
        instruments = {i["instrument_name"]: i for i in snap["instruments"]}
        tickers = snap["tickers"]
        if isinstance(tickers, list):
            tickers = {t["instrument_name"]: t for t in tickers}

        # Capture timestamp in ms (fall back to the first ticker timestamp).
        self.t0_ms = self._iso_ms(self.captured_iso) or int(
            next(iter(tickers.values())).get("timestamp", time.time() * 1000)
        )

        # Pick the expiry nearest to 7 days = "the weekly".
        expiries = sorted({int(i["expiration_timestamp"]) for i in instruments.values()})
        self.expiry_ts = min(
            expiries,
            key=lambda e: abs((e - self.t0_ms) / 1000 / 86400 - 7.0),
        )

        # Freeze the base table for that expiry: (instrument, strike, kind, iv,
        # forward). We re-mark every tick from this captured IV.
        self.base: list[dict] = []
        forward0 = 0.0
        for name, inst in instruments.items():
            if int(inst["expiration_timestamp"]) != self.expiry_ts:
                continue
            tk = tickers.get(name)
            if tk is None:
                continue
            iv = (_f(tk.get("mark_iv")) or 0.0) / 100.0   # decimal
            fwd = _f(tk.get("underlying_price")) or self.index0
            forward0 = fwd  # all same-expiry quotes share one forward
            self.base.append({
                "name": name,
                "strike": float(inst["strike"]),
                "kind": "C" if inst["option_type"] == "call" else "P",
                "iv": iv,
                "oi": _f(tk.get("open_interest")),
                "vol": _f((tk.get("stats") or {}).get("volume")),
            })
        self.forward0 = forward0 or self.index0
        # Constant basis ratio forward/index, carried as the index moves.
        self.basis = self.forward0 / self.index0

        # How many ticks: sim_days of calendar time at tick_seconds cadence.
        self.n_ticks = max(1, int(self.cfg.sim_days * 86400 / self.cfg.tick_seconds))

        # GBM volatility: use the median captured IV so the path is realistic.
        ivs = [b["iv"] for b in self.base if b["iv"] and b["iv"] > 0]
        self.path_vol = float(np.median(ivs)) if ivs else 0.6

    # --- the actual generator -------------------------------------------
    def chains(self) -> Iterator[Chain]:
        rng = np.random.default_rng(self.cfg.sim_seed)
        dt_years = self.cfg.tick_seconds / (365.0 * 86400.0)
        mu = 0.0  # drift-free GBM (risk-neutral-ish; we are not forecasting)
        index = self.index0
        for i in range(self.n_ticks):
            ts = self.t0_ms + int(i * self.cfg.tick_seconds * 1000)
            # Evolve the index with one GBM step (i==0 keeps the captured level).
            if i > 0:
                z = rng.standard_normal()
                index *= math.exp(
                    (mu - 0.5 * self.path_vol ** 2) * dt_years
                    + self.path_vol * math.sqrt(dt_years) * z
                )
            forward = index * self.basis
            days = max(0.0, (self.expiry_ts - ts) / 1000 / 86400)
            T = days / 365.0
            quotes: list[OptionQuote] = []
            for b in self.base:
                iv = b["iv"]
                # bs_price returns the premium in USD; Deribit quotes premiums in
                # BTC (coin), so divide by the forward to match the convention.
                mark_usd = pricing.bs_price(forward, b["strike"], T, iv, kind=b["kind"])
                mark = mark_usd / forward if forward > 0 else 0.0
                # Greeks on the FORWARD so strategies can use chain.nearest_delta.
                if T > 0 and iv > 0:
                    g = pricing.greeks(forward, b["strike"], T, iv, kind=b["kind"])
                else:
                    g = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}
                # A token spread so the SimBroker has a bid/ask to cross.
                half = max(0.0005, 0.01 * mark)
                quotes.append(OptionQuote(
                    instrument_name=b["name"],
                    strike=b["strike"],
                    expiry_ts=self.expiry_ts,
                    kind=b["kind"],
                    bid=max(0.0, mark - half),
                    ask=mark + half,
                    mark=mark,
                    mark_iv=iv,
                    delta=g["delta"], gamma=g["gamma"],
                    vega=g["vega"], theta=g["theta"],
                    open_interest=b["oi"], volume=b["vol"],
                ))
            yield Chain(
                ts=ts, index=index, forward=forward,
                expiry_ts=self.expiry_ts, days_to_expiry=days, quotes=quotes,
            )

    @staticmethod
    def _iso_ms(iso: str):
        if not iso:
            return None
        try:
            import datetime as _dt
            return int(_dt.datetime.fromisoformat(iso).timestamp() * 1000)
        except (ValueError, TypeError):
            return None


def _f(x):
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def make_feed(cfg: Config, client=None) -> MarketFeed:
    """Factory the runner uses: ReplayFeed in sim, LiveFeed in live."""
    if cfg.mode == "live":
        if client is None:
            raise ValueError("live mode needs a DeribitClient")
        return LiveFeed(client, cfg)
    return ReplayFeed(cfg)
