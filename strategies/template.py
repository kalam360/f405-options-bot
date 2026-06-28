"""YOUR STARTING POINT — fill in MyStrategy and MyRisk.

This file is wired so the bot runs out of the box (it just does nothing yet).
Run it first to see the loop work and a journal appear:

    uv run python -m botkit.runner --config config.example.yaml \
        --strategy strategies.template:MyStrategy \
        --risk strategies.template:MyRisk

Then make it trade. You implement TWO classes:

  * MyStrategy  — looks at the chain + your account, returns the Orders you want.
  * MyRisk      — approves/resizes/drops those orders, and can halt the bot.

Read botkit/strategy.py and botkit/risk.py for the full interface, and use the
Chain helpers: chain.atm("C"/"P"), chain.nearest_delta(target, kind),
chain.calls()/puts(). Pricing/Greeks live in botkit.pricing.

Golden rules to keep in mind:
  * size is in signed contracts (1 = 1 BTC); orders use a positive `amount`.
  * IV is a decimal; convert option premiums to USD with chain.forward.
  * Watch your net Greeks in `account.greeks` — short vol blows up on a move.
"""
from __future__ import annotations

from botkit import Strategy, RiskManager, RiskLimits
from botkit.types import Chain, AccountState, Order, Fill


class MyStrategy(Strategy):
    """A do-nothing stub. Replace on_chain with your trading logic."""
    name = "my_strategy"

    def on_start(self, account: AccountState) -> None:
        # TODO (optional): set up any state you want to carry across ticks.
        pass

    def on_chain(self, chain: Chain, account: AccountState) -> list[Order]:
        # TODO: decide what to trade this tick and return a list of Orders.
        #
        # Example to get you started (commented out so the stub is a safe no-op):
        #   atm_call = chain.atm("C")
        #   if atm_call and not account.positions:
        #       return [Order(atm_call.instrument_name, "sell", 1.0, label="atm_short")]
        #
        # Hints:
        #   * chain.nearest_delta(0.25, "P") -> the ~25-delta put.
        #   * account.greeks.delta / .vega tell you your current exposure.
        #   * Return [] to do nothing this tick.
        return []

    def on_fill(self, fill: Fill) -> None:
        # TODO (optional): react to an execution (update internal state, log, ...).
        pass


class MyRisk(RiskManager):
    """A pass-through stub with default (loose) limits. Tighten this!"""
    name = "my_risk"

    def __init__(self) -> None:
        # TODO: choose and defend your own RiskLimits in your report.
        self.limits = RiskLimits()

    def vet(self, orders: list[Order], chain: Chain, account: AccountState) -> list[Order]:
        # TODO: drop or resize orders that would breach self.limits
        #       (e.g. cap |net delta|, |net vega|, gross contracts, margin use).
        # The stub approves everything — DO NOT ship this; it will blow up.
        return orders

    def should_halt(self, account: AccountState) -> bool:
        # TODO: add your kill-switch (e.g. drawdown from peak equity).
        # The default trips only on liquidation:
        return super().should_halt(account)
