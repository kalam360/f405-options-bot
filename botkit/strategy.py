"""The Strategy interface — THIS is the part you write.

A strategy looks at the current chain + your account and returns the orders it
wants to send. It does NOT touch the exchange, manage risk, or track P&L — the
runner, risk manager and broker do that. Keep it pure and decision-only: same
inputs -> same orders. That makes it testable in sim before it ever trades live.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from .types import Chain, AccountState, Order, Fill


class Strategy(ABC):
    name: str = "unnamed"

    def on_start(self, account: AccountState) -> None:
        """Called once before the first chain. Set up state here if you need to."""

    @abstractmethod
    def on_chain(self, chain: Chain, account: AccountState) -> list[Order]:
        """Called every tick with the latest front-weekly chain and your account.

        Return the orders you want to place this tick (an empty list = do nothing).
        Orders flow through your RiskManager.vet() before they reach the broker, so
        return your *intent* here; let the risk layer enforce limits.
        """
        raise NotImplementedError

    def on_fill(self, fill: Fill) -> None:
        """Called after each fill, if you want to react to executions."""
