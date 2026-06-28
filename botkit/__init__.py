"""botkit — the provided trading framework for the F405 options-bot assignment.

You implement `Strategy` and `RiskManager`; botkit handles the exchange, the
paper-trading loop, position/P&L tracking and the journal that gets you graded.

The pricing/Greeks functions (bs_price, greeks, implied_vol) are the same tested
library from the lecture notebook — use them in your strategy.
"""
from .types import (
    OptionQuote, Chain, Order, Fill, PositionLeg, Greeks, AccountState,
)
from .strategy import Strategy
from .risk import RiskManager, RiskLimits
from .config import Config
from .pricing import bs_price, greeks, implied_vol, d1d2

__all__ = [
    "OptionQuote", "Chain", "Order", "Fill", "PositionLeg", "Greeks", "AccountState",
    "Strategy", "RiskManager", "RiskLimits", "Config",
    "bs_price", "greeks", "implied_vol", "d1d2",
    "run",
]


def __getattr__(name):
    # Lazy export so `python -m botkit.runner` doesn't import the runner twice
    # (which triggers a harmless-but-noisy RuntimeWarning from runpy).
    if name == "run":
        from .runner import run
        return run
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
