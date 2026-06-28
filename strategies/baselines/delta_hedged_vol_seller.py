"""Baseline #3 — DELTA-HEDGED VOL SELLER (the benchmark you must beat).

Same premium-harvesting idea as the naive short straddle — sell the ATM weekly
call and put to collect theta — but with the one discipline that keeps a vol
seller alive: **re-hedge the net delta back toward zero every tick** (gamma
scalping). By neutralising direction continuously, the position keeps its short
gamma / short theta *carry* without taking the directional bet that liquidates
the naive version on a move.

Why hedging is the whole game (tie this to the lecture):
  * A short straddle is delta-neutral *only at the instant you put it on*. As the
    underlying moves, short gamma makes net delta run **against** you — long when
    you want to be short and vice-versa. Left alone, that is the blow-up.
  * Re-hedging to ~0 delta locks in the realised move as a (small) hedging cost
    and lets theta accrue. The trade becomes a bet on **realised vol < implied
    vol**, not on price direction — which is the bet a vol desk actually wants.

Hedging instrument — note for students: on the live Deribit desk you would hedge
delta with the **perpetual future** (pure delta 1, no gamma/vega). Our offline
chain is options-only, so we use the cleanest available proxy: the **deepest
in-the-money call**, whose delta is ~1 and whose gamma/vega are ~0 — i.e. it
behaves almost exactly like holding the underlying. We size the hedge from the
account's net delta (``account.greeks.delta``), which already includes every leg.

Paired with ``HedgedRisk``: bounds net vega / gross size and, crucially, runs a
**drawdown kill-switch that flattens BEFORE liquidation** — the survival layer
the naive baseline lacks.
"""
from __future__ import annotations

from botkit import Strategy, RiskManager, RiskLimits
from botkit.types import Chain, AccountState, Order, Fill

# A PRUDENT short-vol size. Note this is much smaller than the naive baseline's
# 10 contracts: a real vol desk sizes the tail it can survive, not the premium it
# can grab. Smaller size + hedging + a kill-switch is what separates this
# "benchmark to beat" from the bomb.
STRADDLE_SIZE = 3.0

# Don't re-hedge micro-noise: only act when |net delta| exceeds this band (in
# BTC), and round hedge orders to this contract step. The deep-ITM call we hedge
# with has a wide bid/ask in BTC terms, so hedging on every tiny wiggle would
# bleed the premium away in spread + fees. A band keeps hedging cheap.
HEDGE_DEADBAND = 0.5
HEDGE_STEP = 0.1


class DeltaHedgedVolSeller(Strategy):
    """Short ATM straddle + continuous delta hedge toward ~0 net delta."""

    name = "delta_hedged_vol_seller"

    def on_start(self, account: AccountState) -> None:
        self._straddle_on = False

    def on_chain(self, chain: Chain, account: AccountState) -> list[Order]:
        orders: list[Order] = []

        # 1) Put the short straddle on once (the premium-harvesting core).
        if not self._straddle_on:
            call = chain.atm("C")
            put = chain.atm("P")
            if call is None or put is None:
                return []
            self._straddle_on = True
            # Return now; next tick we start hedging with the straddle in the book
            # and a fresh, accurate net-delta reading from the portfolio.
            return [
                Order(call.instrument_name, "sell", STRADDLE_SIZE, label="straddle_call"),
                Order(put.instrument_name, "sell", STRADDLE_SIZE, label="straddle_put"),
            ]

        # 2) Re-hedge net delta toward zero using a deep-ITM call (~delta 1) as a
        #    stand-in for the underlying.
        hedge = chain.nearest_delta(1.0, "C")  # deepest ITM call available
        if hedge is None or not hedge.delta:
            return orders

        residual = account.greeks.delta  # net delta across ALL legs, in BTC
        if abs(residual) <= HEDGE_DEADBAND:
            return orders  # already flat enough — don't churn.

        # Contracts of the hedge instrument needed to cancel the residual delta:
        #   residual + qty * hedge.delta = 0  ->  qty = -residual / hedge.delta
        qty = -residual / hedge.delta
        side = "buy" if qty > 0 else "sell"
        amount = round(abs(qty) / HEDGE_STEP) * HEDGE_STEP
        if amount < HEDGE_STEP:
            return orders

        orders.append(Order(hedge.instrument_name, side, amount, label="delta_hedge"))
        return orders

    def on_fill(self, fill: Fill) -> None:
        pass


class HedgedRisk(RiskManager):
    """A REAL risk layer: bound vega/gross size and flatten on a drawdown.

    This is the survival discipline the naive baseline is missing. It is still
    intentionally simple (it is a baseline, not the answer) — tighten and extend
    it in your own ``MyRisk``.
    """

    name = "hedged_risk"

    def __init__(self) -> None:
        # Tighter than the loose defaults, but still a baseline. The kill-switch
        # is the important part: stop the loss before the exchange does.
        self.limits = RiskLimits(
            max_net_vega_usd=80_000.0,
            max_gross_contracts=80.0,
            kill_switch_drawdown_pct=0.20,  # flatten after a 20% drop from peak.
        )
        self._peak_equity = 0.0

    def vet(self, orders: list[Order], chain: Chain, account: AccountState) -> list[Order]:
        approved: list[Order] = []
        # Track gross size as we go so a batch can't collectively breach the cap.
        gross = sum(abs(leg.size) for leg in account.positions.values())
        for o in orders:
            # Always allow the delta hedge through: it REDUCES directional risk,
            # which is exactly what the risk layer wants. Capping it would defeat
            # the hedge and re-create the naive blow-up.
            if o.label == "delta_hedge":
                approved.append(o)
                continue
            # Otherwise enforce the gross-contracts ceiling on new risk.
            if gross + o.amount > self.limits.max_gross_contracts:
                continue  # drop the order — it would over-extend the book.
            gross += o.amount
            approved.append(o)
        return approved

    def should_halt(self, account: AccountState) -> bool:
        # Kill-switch: remember the high-water mark and halt+flatten if equity
        # falls more than the configured fraction below it — BEFORE liquidation.
        self._peak_equity = max(self._peak_equity, account.equity_usd)
        if account.liquidated:
            return True
        if self._peak_equity > 0:
            drawdown = 1.0 - account.equity_usd / self._peak_equity
            if drawdown >= self.limits.kill_switch_drawdown_pct:
                return True
        return False
