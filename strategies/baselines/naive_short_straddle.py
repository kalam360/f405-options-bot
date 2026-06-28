"""Baseline #1 — the NAIVE SHORT STRADDLE (the cautionary "bomb").

The textbook "easy money" options trade: sell the at-the-money call AND the
at-the-money put on the front weekly, pocket both premiums, and wait for theta
to decay them to zero. For a few quiet days it prints money. Then the underlying
makes one real move into expiry and the position's **short gamma** turns that
move into an accelerating loss — and with no risk layer to stop it, the account
gets liquidated. That is the whole point of shipping this: run it in sim and
*watch it blow up*.

Why it blows up (tie this to the lecture):
  * A short straddle is **short gamma** and **short vega**. Near expiry gamma is
    huge, so delta swings violently with the underlying and the P&L is convex
    *against* you — losses grow faster than premium ever paid.
  * We size it aggressively (many contracts on a 1-BTC account) so the tail is
    fatal, not just uncomfortable — exactly what an un-risk-managed desk does.

This file pairs the strategy with ``NaiveRisk``, a DO-NOTHING risk manager with
the loose default limits and no kill-switch. That is intentional: it lets the
bomb go off. Do NOT submit this — see ``delta_hedged_vol_seller`` for survival.
"""
from __future__ import annotations

from botkit import Strategy, RiskManager, RiskLimits
from botkit.types import Chain, AccountState, Order, Fill

# How many contracts of EACH leg to sell. Deliberately large for a 1-BTC account
# so the short-gamma tail is fatal and the blow-up is visible in the journal.
STRADDLE_SIZE = 10.0


class NaiveShortStraddle(Strategy):
    """Sell the ATM weekly straddle once, then just hold it into expiry."""

    name = "naive_short_straddle"

    def on_start(self, account: AccountState) -> None:
        # Have we already put the straddle on? (We sell it once per weekly cycle;
        # the sim runs a single weekly expiry, so that means once.)
        self._sold = False

    def on_chain(self, chain: Chain, account: AccountState) -> list[Order]:
        if self._sold:
            return []  # nothing to do — we just sit on the short straddle.

        call = chain.atm("C")
        put = chain.atm("P")
        if call is None or put is None:
            return []  # no ATM quotes this tick; try again next tick.

        self._sold = True
        # Sell the call and the put at the same (ATM) strike: a short straddle.
        return [
            Order(call.instrument_name, "sell", STRADDLE_SIZE, label="straddle_call"),
            Order(put.instrument_name, "sell", STRADDLE_SIZE, label="straddle_put"),
        ]

    def on_fill(self, fill: Fill) -> None:
        pass


class NaiveRisk(RiskManager):
    """NO real risk management — the loose defaults, pass everything through.

    This is what NOT to do. ``vet`` approves every order untouched and
    ``should_halt`` only trips once the account is already liquidated (too late).
    Contrast with ``HedgedRisk`` in the delta-hedged baseline.
    """

    name = "naive_risk"

    def __init__(self) -> None:
        self.limits = RiskLimits()  # the loose, out-of-the-box defaults.

    def vet(self, orders: list[Order], chain: Chain, account: AccountState) -> list[Order]:
        return orders  # approve everything, no questions asked.

    # should_halt: inherit the default (only halts when account.liquidated).
