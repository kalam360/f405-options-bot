"""Run configuration. Loaded from a YAML file and/or environment variables.

Secrets (API keys) come ONLY from the environment, never the YAML — so you never
commit a key. See .env.example.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field

from .risk import RiskLimits

Mode = str  # "sim" | "live"


@dataclass
class Config:
    mode: Mode = "sim"                       # "sim" = offline replay, "live" = Deribit testnet
    currency: str = "BTC"
    expiry_selector: str = "front_weekly"    # which expiry to trade
    tick_seconds: float = 60.0               # how often the runner polls the chain
    start_equity_btc: float = 1.0            # sim starting balance
    journal_dir: str = "runs/latest"
    risk: RiskLimits = field(default_factory=RiskLimits)

    # sim-mode data source (one of these); ignored when mode == "live"
    sim_snapshot: str | None = "data/deribit_snapshot.json"  # replay a captured chain
    sim_days: float = 7.0                    # length of the synthetic run, in days
    sim_seed: int = 0

    # live-mode (Deribit testnet) — secrets from env, NOT from yaml
    @property
    def client_id(self) -> str:
        return os.environ.get("DERIBIT_CLIENT_ID", "")

    @property
    def client_secret(self) -> str:
        return os.environ.get("DERIBIT_CLIENT_SECRET", "")

    base_url: str = "https://test.deribit.com"   # ALWAYS testnet for this assignment

    @classmethod
    def load(cls, path: str | None = None) -> "Config":
        """Load from a YAML file if given, overlaying env where relevant."""
        cfg = cls()
        if path and os.path.exists(path):
            import yaml  # pyyaml is a dependency
            data = yaml.safe_load(open(path)) or {}
            risk = data.pop("risk", None)
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
            if risk:
                cfg.risk = RiskLimits(**{**cfg.risk.__dict__, **risk})
        if os.environ.get("BOT_MODE"):
            cfg.mode = os.environ["BOT_MODE"]
        return cfg
