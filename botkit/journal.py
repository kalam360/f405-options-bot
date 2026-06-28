"""Journal: the run's permanent record — and the GRADING CONTRACT.

Every run writes three files into its `journal_dir`:
  * `trades.csv` — one row per fill.
  * `equity.csv` — one row per tick (mark-to-market snapshot).
  * `meta.json`  — run-level metadata (strategy, mode, span, start equity).

The CSV column orders below are FIXED — `score.py`, the leaderboard poller and
the autograder all read them by name/position. Do not reorder or rename columns.
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import os
from typing import Optional

from .types import AccountState, Fill

TRADES_HEADER = [
    "ts", "iso", "instrument", "side", "amount",
    "price_btc", "price_usd", "fee_btc", "strategy", "label",
]
EQUITY_HEADER = [
    "ts", "iso", "equity_usd", "cash_btc", "index", "forward",
    "net_delta", "net_vega_usd", "net_theta_usd", "margin_util",
    "realized_usd", "unrealized_usd", "liquidated",
]


def _iso(ts_ms: int) -> str:
    """ms-since-epoch -> ISO-8601 UTC string."""
    return dt.datetime.fromtimestamp(ts_ms / 1000, tz=dt.timezone.utc).isoformat()


class Journal:
    def __init__(self, journal_dir: str) -> None:
        self.dir = journal_dir
        os.makedirs(self.dir, exist_ok=True)
        self.trades_path = os.path.join(self.dir, "trades.csv")
        self.equity_path = os.path.join(self.dir, "equity.csv")
        self.meta_path = os.path.join(self.dir, "meta.json")

        # Fresh files each run, headers written once.
        self._tf = open(self.trades_path, "w", newline="")
        self._ef = open(self.equity_path, "w", newline="")
        self._tw = csv.writer(self._tf)
        self._ew = csv.writer(self._ef)
        self._tw.writerow(TRADES_HEADER)
        self._ew.writerow(EQUITY_HEADER)

        # Caches so trade rows can report USD using the latest forward, and so
        # meta.json can record the run span + starting equity.
        self._last_forward: float = 0.0
        self._start_ts: Optional[int] = None
        self._end_ts: Optional[int] = None
        self._start_equity_usd: Optional[float] = None
        self._meta: dict = {}

    # --- per-tick equity row --------------------------------------------
    def equity(self, state: AccountState) -> None:
        self._last_forward = state.forward
        if self._start_ts is None:
            self._start_ts = state.ts
            self._start_equity_usd = state.equity_usd
        self._end_ts = state.ts
        self._ew.writerow([
            state.ts, _iso(state.ts),
            f"{state.equity_usd:.6f}", f"{state.cash_btc:.8f}",
            f"{state.index:.2f}", f"{state.forward:.2f}",
            f"{state.greeks.delta:.6f}", f"{state.greeks.vega:.4f}",
            f"{state.greeks.theta:.4f}", f"{state.margin_util:.6f}",
            f"{state.pnl_realized_usd:.6f}", f"{state.pnl_unrealized_usd:.6f}",
            int(bool(state.liquidated)),
        ])
        self._ef.flush()

    # --- per-fill trade row ---------------------------------------------
    def trade(self, fill: Fill, strategy: str) -> None:
        price_usd = fill.price * self._last_forward
        self._tw.writerow([
            fill.ts, _iso(fill.ts), fill.instrument_name, fill.side,
            f"{fill.amount:.6f}", f"{fill.price:.8f}", f"{price_usd:.4f}",
            f"{fill.fee:.8f}", strategy, fill.order_label,
        ])
        self._tf.flush()

    # --- run-level metadata ---------------------------------------------
    def set_meta(self, **kwargs) -> None:
        self._meta.update(kwargs)

    def close(self) -> None:
        """Flush CSVs and write meta.json. Safe to call once at the end."""
        self._tf.close()
        self._ef.close()
        meta = {
            "start_ts": self._start_ts,
            "end_ts": self._end_ts,
            "start_iso": _iso(self._start_ts) if self._start_ts else None,
            "end_iso": _iso(self._end_ts) if self._end_ts else None,
            "start_equity_usd": self._start_equity_usd,
            **self._meta,
        }
        with open(self.meta_path, "w") as f:
            json.dump(meta, f, indent=2)
