"""Shared data types for the trading framework — the CONTRACT every module agrees on.

Nothing here does I/O or pricing; these are plain data carriers passed between the
feed, the strategy, the risk manager, the broker and the journal. If you change a
field here you change it for everyone, so treat this file as the stable interface.

Conventions used everywhere in botkit:
  * vol / IV is a DECIMAL (0.65 == 65%), never a percent.
  * time-to-expiry is in YEARS.
  * option prices coming in/out of the pricer are in USD; Deribit quotes premiums
    in BTC, so the broker/feed convert with the per-expiry forward.
  * a position `size` is signed: +long, -short, in contracts (1 contract = 1 BTC).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional

Kind = Literal["C", "P"]
Side = Literal["buy", "sell"]
OrderType = Literal["limit", "market"]


@dataclass(frozen=True)
class OptionQuote:
    """One option instrument at one instant, as seen on the chain."""
    instrument_name: str          # e.g. "BTC-4JUL25-60000-C"
    strike: float
    expiry_ts: int                # ms since epoch (Deribit expiration_timestamp)
    kind: Kind
    bid: Optional[float]          # in BTC (coin) — Deribit convention
    ask: Optional[float]
    mark: Optional[float]         # in BTC
    mark_iv: Optional[float]      # DECIMAL (mark_iv from Deribit / 100)
    delta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    theta: Optional[float] = None
    open_interest: Optional[float] = None
    volume: Optional[float] = None

    @property
    def mid(self) -> Optional[float]:
        if self.bid is not None and self.ask is not None and self.ask >= self.bid:
            return 0.5 * (self.bid + self.ask)
        return self.mark


@dataclass
class Chain:
    """A snapshot of ONE expiry's option chain (the front weekly, by default).

    `forward` is that expiry's forward price (Deribit underlying_price); use it,
    not `index`, when pricing/inverting IV — see the lecture notebook.
    """
    ts: int                       # snapshot time, ms since epoch
    index: float                  # BTC spot index, USD
    forward: float                # this expiry's forward, USD
    expiry_ts: int                # ms since epoch
    days_to_expiry: float         # calendar days (can be fractional)
    quotes: list[OptionQuote] = field(default_factory=list)

    def by_name(self, name: str) -> Optional[OptionQuote]:
        return next((q for q in self.quotes if q.instrument_name == name), None)

    def calls(self) -> list[OptionQuote]:
        return sorted([q for q in self.quotes if q.kind == "C"], key=lambda q: q.strike)

    def puts(self) -> list[OptionQuote]:
        return sorted([q for q in self.quotes if q.kind == "P"], key=lambda q: q.strike)

    def atm(self, kind: Kind = "C") -> Optional[OptionQuote]:
        pool = self.calls() if kind == "C" else self.puts()
        return min(pool, key=lambda q: abs(q.strike - self.forward)) if pool else None

    def nearest_delta(self, target: float, kind: Kind) -> Optional[OptionQuote]:
        pool = [q for q in (self.calls() if kind == "C" else self.puts()) if q.delta is not None]
        return min(pool, key=lambda q: abs(abs(q.delta) - abs(target))) if pool else None


@dataclass(frozen=True)
class Order:
    """An instruction the strategy emits; the risk manager may resize or drop it."""
    instrument_name: str
    side: Side
    amount: float                 # contracts (BTC), > 0
    type: OrderType = "market"
    price: Optional[float] = None  # required for limit (in BTC)
    label: str = ""               # free tag, echoed into the journal
    reduce_only: bool = False


@dataclass(frozen=True)
class Fill:
    """A (partial) execution returned by the broker."""
    ts: int
    instrument_name: str
    side: Side
    amount: float                 # contracts actually filled
    price: float                  # fill price in BTC
    fee: float                    # in BTC
    order_label: str = ""


@dataclass
class PositionLeg:
    instrument_name: str
    size: float                   # signed contracts: +long / -short
    avg_price: float              # in BTC
    strike: float
    kind: Kind
    expiry_ts: int
    mark: Optional[float] = None  # latest mark in BTC


@dataclass
class Greeks:
    delta: float = 0.0            # in BTC per $1 of underlying * ... (portfolio net)
    gamma: float = 0.0
    vega: float = 0.0             # USD per 1.00 vol
    theta: float = 0.0            # USD per year


@dataclass
class AccountState:
    """Everything the strategy/risk manager need to decide the next move."""
    ts: int
    equity_usd: float             # total account value, marked to market, USD
    cash_btc: float               # free balance in BTC
    index: float                  # BTC spot, USD
    forward: float                # front-weekly forward, USD
    positions: dict[str, PositionLeg] = field(default_factory=dict)
    greeks: Greeks = field(default_factory=Greeks)
    pnl_realized_usd: float = 0.0
    pnl_unrealized_usd: float = 0.0
    margin_util: float = 0.0      # 0..1 fraction of balance used as margin
    liquidated: bool = False
