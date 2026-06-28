"""Baseline #2 — BUY AND HOLD ONE ATM CALL (the theta bleed).

The mirror image of the short straddle. Instead of selling vol we *buy* it: one
at-the-money call on the front weekly, held untouched into expiry. This is the
most intuitive "I'm bullish, buy a call" trade, and it shows students the cost of
being **long an option you don't trade around**:

  * A long option is **long theta-negative** — every day that passes, time value
    decays out of the premium. With a drift-free underlying the call slowly
    bleeds to its intrinsic value; in sim you watch equity grind *down* even
    though nothing dramatic happens.
  * It is **long gamma / long vega**, so a big up-move or a vol spike *can* pay
    off — but on an average path the carry (theta) wins and you lose the premium.

The lesson: optionality is not free. Holding a wasting asset and hoping is not a
strategy; you have to earn back theta (by being right on direction or by actively
trading the gamma). Pairs with a pass-through risk manager — a single long call
can lose at most its premium, so there is nothing to hedge or halt.
"""
from __future__ import annotations

from botkit import Strategy, RiskManager, RiskLimits
from botkit.types import Chain, AccountState, Order, Fill

# How many ATM calls to buy and hold. One contract = 1 BTC of notional.
CALL_SIZE = 1.0


class BuyAndHoldCall(Strategy):
    """Buy one ATM weekly call on the first tick, then hold it to expiry."""

    name = "buy_and_hold_call"

    def on_start(self, account: AccountState) -> None:
        self._bought = False

    def on_chain(self, chain: Chain, account: AccountState) -> list[Order]:
        if self._bought:
            return []  # hold — no further trading, just let theta do its thing.

        call = chain.atm("C")
        if call is None:
            return []

        self._bought = True
        return [Order(call.instrument_name, "buy", CALL_SIZE, label="hold_call")]

    def on_fill(self, fill: Fill) -> None:
        pass


class BuyHoldRisk(RiskManager):
    """A pass-through risk manager. A long call's loss is capped at its premium,
    so there is no tail to manage and no kill-switch to trip."""

    name = "buy_hold_risk"

    def __init__(self) -> None:
        self.limits = RiskLimits()

    def vet(self, orders: list[Order], chain: Chain, account: AccountState) -> list[Order]:
        return orders

    # should_halt: default (liquidation only) — a long call cannot get liquidated.
