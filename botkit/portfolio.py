"""Portfolio: positions, cash, mark-to-market equity and net Greeks.

The Portfolio is botkit's accountant. The broker hands it `Fill`s; it keeps
signed positions and a BTC cash balance, marks everything to the latest chain,
and produces an `AccountState` the strategy/risk manager read each tick.

Money conventions (see the golden rules):
  * Premiums are in BTC. Buying an option pays premium out of cash; selling one
    takes it in. Fees are paid in BTC.
  * To put a number in USD we convert BTC option premiums with the per-expiry
    FORWARD (`chain.forward`), and the account's BTC cash with the spot `index`.
  * Greeks are computed analytically on the FORWARD via `pricing.greeks`, signed
    by position size, in the units `types.Greeks` documents (delta in BTC, vega
    USD per 1.00 vol, theta USD per year).
"""
from __future__ import annotations
from typing import Optional

from . import pricing
from .types import AccountState, Chain, Fill, Greeks, PositionLeg


class Portfolio:
    def __init__(self, start_cash_btc: float, pricing_mod=pricing) -> None:
        self.cash_btc: float = float(start_cash_btc)
        self.pricing = pricing_mod
        self.positions: dict[str, PositionLeg] = {}
        self.realized_btc: float = 0.0      # locked P&L, in BTC

    # --- applying fills --------------------------------------------------
    def apply(self, fill: Fill) -> None:
        """Update cash + positions for one execution (signed contracts)."""
        signed = fill.amount if fill.side == "buy" else -fill.amount
        # Cash: buying pays premium (-), selling receives it (+); fees always cost.
        self.cash_btc += -signed * fill.price
        self.cash_btc -= fill.fee

        leg = self.positions.get(fill.instrument_name)
        if leg is None:
            # Brand-new position; learn its static details from the name.
            strike, kind = _parse_name(fill.instrument_name)
            leg = PositionLeg(
                instrument_name=fill.instrument_name, size=0.0, avg_price=0.0,
                strike=strike, kind=kind, expiry_ts=0, mark=fill.price,
            )
            self.positions[fill.instrument_name] = leg

        old = leg.size
        new = old + signed
        if old == 0 or (old > 0) == (signed > 0):
            # Opening or adding on the same side: weighted-average the entry.
            denom = abs(old) + abs(signed)
            leg.avg_price = (abs(old) * leg.avg_price + abs(signed) * fill.price) / denom
        else:
            # Reducing / closing / flipping: realise P&L on the closed amount.
            closed = min(abs(signed), abs(old))
            side_sign = 1.0 if old > 0 else -1.0   # long realises (price-avg)
            self.realized_btc += closed * (fill.price - leg.avg_price) * side_sign
            if (new > 0) != (old > 0) and new != 0:
                # Flipped through zero: the remainder opens fresh at fill price.
                leg.avg_price = fill.price
        leg.size = new
        if abs(leg.size) < 1e-12:
            # Fully closed — drop it so it stops showing in net Greeks.
            del self.positions[fill.instrument_name]

    # --- marking ---------------------------------------------------------
    def mark(self, chain: Chain) -> None:
        """Refresh each leg's mark from the latest chain."""
        for name, leg in self.positions.items():
            q = chain.by_name(name)
            if q is not None and q.mark is not None:
                leg.mark = float(q.mark)

    # --- the snapshot the rest of the bot reads --------------------------
    def state(self, chain: Chain) -> AccountState:
        index = chain.index
        forward = chain.forward
        T = max(0.0, chain.days_to_expiry) / 365.0

        net = Greeks()
        positions_value_btc = 0.0
        unreal_btc = 0.0
        short_margin_usd = 0.0
        for name, leg in self.positions.items():
            mark = leg.mark if leg.mark is not None else 0.0
            positions_value_btc += leg.size * mark
            unreal_btc += leg.size * (mark - leg.avg_price)
            q = chain.by_name(name)
            iv = q.mark_iv if (q is not None and q.mark_iv) else None
            if iv and T > 0:
                g = self.pricing.greeks(forward, leg.strike, T, iv, kind=leg.kind)
                net.delta += leg.size * g["delta"]
                net.gamma += leg.size * g["gamma"]
                net.vega += leg.size * g["vega"]
                net.theta += leg.size * g["theta"]
            if leg.size < 0:
                # Rough short-option margin estimate (premium + 15% of forward).
                short_margin_usd += abs(leg.size) * (mark * forward + 0.15 * forward)

        # Account equity: BTC cash valued at spot, option premiums at the forward.
        equity_usd = self.cash_btc * index + positions_value_btc * forward
        unrealized_usd = unreal_btc * forward
        realized_usd = self.realized_btc * forward
        margin_util = (short_margin_usd / equity_usd) if equity_usd > 0 else 1.0
        liquidated = equity_usd <= 0.0

        return AccountState(
            ts=chain.ts,
            equity_usd=equity_usd,
            cash_btc=self.cash_btc,
            index=index,
            forward=forward,
            positions=dict(self.positions),
            greeks=net,
            pnl_realized_usd=realized_usd,
            pnl_unrealized_usd=unrealized_usd,
            margin_util=max(0.0, margin_util),
            liquidated=liquidated,
        )


def _parse_name(name: str) -> tuple[float, str]:
    """Pull strike + kind out of an instrument name like BTC-4JUL25-60000-C."""
    parts = name.split("-")
    try:
        strike = float(parts[2])
    except (IndexError, ValueError):
        strike = 0.0
    kind = "C" if name.endswith("C") else "P"
    return strike, kind
