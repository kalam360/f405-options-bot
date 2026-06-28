"""The runner: the event loop that ties the whole bot together.

    feed -> strategy -> risk -> broker -> portfolio -> journal

Each tick we mark the book, snapshot the account, log equity, ask the risk
manager whether to halt, then let the strategy propose orders, vet them, execute
them and record the fills. In `sim` mode every piece is offline and
deterministic, so `python -m botkit.runner` produces a full journal with no keys
and no network — exactly what CI and graders run.

CLI:
    uv run python -m botkit.runner \
        --config config.example.yaml \
        --strategy strategies.template:MyStrategy \
        --risk strategies.template:MyRisk
"""
from __future__ import annotations
import argparse
import importlib
from typing import Optional

from .broker import make_broker
from .config import Config
from .feed import make_feed
from .journal import Journal
from .portfolio import Portfolio
from .risk import RiskManager
from .strategy import Strategy
from .types import Chain, Order


def _load_obj(spec: str):
    """Turn a 'package.module:ClassName' string into an instantiated object."""
    if ":" not in spec:
        raise ValueError(f"expected 'module:Class', got {spec!r}")
    module_name, class_name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    return cls()


def _flatten_orders(state) -> list[Order]:
    """Reduce-only market orders that close every open position."""
    orders: list[Order] = []
    for name, leg in state.positions.items():
        if leg.size > 0:
            orders.append(Order(name, "sell", abs(leg.size), label="flatten", reduce_only=True))
        elif leg.size < 0:
            orders.append(Order(name, "buy", abs(leg.size), label="flatten", reduce_only=True))
    return orders


def run(cfg: Config, strategy: Strategy, risk: RiskManager) -> dict:
    """Run the full loop and return a small summary dict (also in meta.json)."""
    # Live mode needs a real client; sim mode stays fully offline.
    client = None
    if cfg.mode == "live":
        from .deribit import DeribitClient
        client = DeribitClient(cfg.client_id, cfg.client_secret, cfg.base_url)
        client.auth()

    feed = make_feed(cfg, client)
    broker = make_broker(cfg, client)
    pf = Portfolio(cfg.start_equity_btc)
    jr = Journal(cfg.journal_dir)

    ticks = 0
    fills_count = 0
    halted = False
    started = False

    for chain in feed.chains():  # type: Chain
        pf.mark(chain)
        state = pf.state(chain)

        if not started:
            strategy.on_start(state)
            started = True

        jr.equity(state)
        ticks += 1

        # Kill-switch first: if we must halt, flatten and stop opening risk.
        if risk.should_halt(state):
            for f in broker.execute(_flatten_orders(state), chain):
                pf.apply(f)
                jr.trade(f, strategy.name)
                strategy.on_fill(f)
                fills_count += 1
            halted = True
            break

        # Strategy proposes; risk vets; broker executes.
        orders = strategy.on_chain(chain, state) or []
        orders = risk.vet(orders, chain, state) or []
        for f in broker.execute(orders, chain):
            pf.apply(f)
            jr.trade(f, strategy.name)
            strategy.on_fill(f)
            fills_count += 1

    jr.set_meta(
        strategy=strategy.name,
        risk=getattr(risk, "name", "unnamed"),
        mode=cfg.mode,
        ticks=ticks,
        fills=fills_count,
        halted=halted,
    )
    jr.close()

    summary = {
        "strategy": strategy.name,
        "mode": cfg.mode,
        "ticks": ticks,
        "fills": fills_count,
        "halted": halted,
        "journal_dir": cfg.journal_dir,
        "start_equity_usd": jr._start_equity_usd,
    }
    if client is not None:
        client.close()
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Run the F405 options bot (sim or live).")
    ap.add_argument("--config", default=None, help="path to a YAML config")
    ap.add_argument("--strategy", required=True, help="module:Class for the Strategy")
    ap.add_argument("--risk", required=True, help="module:Class for the RiskManager")
    ap.add_argument("--mode", default=None, choices=["sim", "live"], help="override cfg.mode")
    ap.add_argument("--journal-dir", default=None, help="override cfg.journal_dir")
    args = ap.parse_args(argv)

    cfg = Config.load(args.config)
    if args.mode:
        cfg.mode = args.mode
    if args.journal_dir:
        cfg.journal_dir = args.journal_dir

    strategy = _load_obj(args.strategy)
    risk = _load_obj(args.risk)

    summary = run(cfg, strategy, risk)
    print("run complete:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
