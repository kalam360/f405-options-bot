"""The RiskManager interface — the other part you write, and the one that keeps
you in the competition.

The runner calls `should_halt()` first (your kill-switch) and then `vet()` on
every batch of orders the strategy emits. Your job: stop the bot from doing
something that gets it liquidated. A naive short-vol strategy with no risk layer
WILL blow up on a weekly expiry — that is the whole point of the assignment.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .types import Chain, AccountState, Order


@dataclass
class RiskLimits:
    """Hard limits you choose and defend in your report. The defaults are loose
    on purpose — tightening them is part of the work."""
    max_net_delta: float = 5.0            # |net delta| in BTC
    max_net_vega_usd: float = 50_000.0    # |net vega|, USD per 1.00 vol
    max_gross_contracts: float = 50.0     # sum |size| across legs
    max_contracts_per_instrument: float = 20.0
    max_margin_util: float = 0.5          # refuse new risk above this margin use
    kill_switch_drawdown_pct: float = 0.30  # halt + flatten if equity drops this far from peak


class RiskManager(ABC):
    name: str = "unnamed"

    @abstractmethod
    def vet(self, orders: list[Order], chain: Chain, account: AccountState) -> list[Order]:
        """Approve, resize, or drop the strategy's orders. Return the orders that
        are actually allowed to go to the broker (possibly empty, possibly resized)."""
        raise NotImplementedError

    def should_halt(self, account: AccountState) -> bool:
        """Kill-switch. If this returns True the runner stops opening risk and
        flattens. Override with your own logic; the default trips on liquidation."""
        return account.liquidated
