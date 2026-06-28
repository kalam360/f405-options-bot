"""Brokers: how an Order becomes Fills.

* `SimBroker` — paper fills for offline `sim` mode. A market order fills at the
  quote's mark crossed by half the spread (a small, deterministic slippage), and
  pays a Deribit-style taker fee (0.0003 BTC/contract, capped at 12.5% of the
  premium). No network, no randomness.
* `LiveBroker` — routes real Orders to the Deribit testnet via DeribitClient and
  returns the exchange's fills.

Both satisfy the `Broker` protocol the runner expects: `execute(orders, chain)`
returns fills; `sync(account)` lets a live broker refresh from the exchange.
"""
from __future__ import annotations
from typing import Iterable, Protocol, runtime_checkable

from .types import Chain, Order, Fill, AccountState

# Deribit option taker commission: 0.0003 BTC per contract, capped at 12.5% of
# the option premium (their documented rule). Reused for the sim fee model.
TAKER_FEE_BTC = 0.0003
FEE_CAP_FRAC = 0.125


@runtime_checkable
class Broker(Protocol):
    def execute(self, orders: list[Order], chain: Chain) -> list[Fill]:
        ...

    def sync(self, account: AccountState) -> None:
        ...


class SimBroker:
    """Deterministic paper-fill broker for offline sim runs."""

    def __init__(self, slippage_frac: float = 0.0) -> None:
        # Extra slippage on top of crossing the spread, as a fraction of mark.
        self.slippage_frac = slippage_frac

    def execute(self, orders: list[Order], chain: Chain) -> list[Fill]:
        fills: list[Fill] = []
        for o in orders:
            if o.amount <= 0:
                continue
            q = chain.by_name(o.instrument_name)
            if q is None or q.mark is None:
                continue  # can't fill what we can't see
            sign = 1.0 if o.side == "buy" else -1.0
            mark = float(q.mark)
            # Cross the spread: buy at the ask side, sell at the bid side.
            if q.bid is not None and q.ask is not None and q.ask >= q.bid:
                half = 0.5 * (q.ask - q.bid)
            else:
                half = 0.0
            price = mark + sign * (half + self.slippage_frac * mark)
            price = max(0.0, price)
            fee = min(TAKER_FEE_BTC, FEE_CAP_FRAC * price) * o.amount
            fills.append(Fill(
                ts=chain.ts,
                instrument_name=o.instrument_name,
                side=o.side,
                amount=o.amount,
                price=price,
                fee=fee,
                order_label=o.label,
            ))
        return fills

    def sync(self, account: AccountState) -> None:
        # Nothing to sync: the Portfolio is the source of truth in sim.
        return None


class LiveBroker:
    """Routes orders to the Deribit testnet and returns real fills."""

    def __init__(self, client) -> None:
        self.client = client

    def execute(self, orders: list[Order], chain: Chain) -> list[Fill]:
        fills: list[Fill] = []
        for o in orders:
            if o.amount <= 0:
                continue
            fills.extend(self.client.place_order(o))
        return fills

    def sync(self, account: AccountState) -> None:
        # The live runner re-reads positions/equity from the account summary;
        # this hook is where a richer integration would refresh them.
        return None


def make_broker(cfg, client=None) -> Broker:
    """Factory the runner uses: SimBroker in sim, LiveBroker in live."""
    if cfg.mode == "live":
        if client is None:
            raise ValueError("live mode needs a DeribitClient")
        return LiveBroker(client)
    return SimBroker()
