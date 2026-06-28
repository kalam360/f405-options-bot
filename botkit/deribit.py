"""Deribit **testnet** REST client.

This is the *live* path: it talks to https://test.deribit.com over HTTPS using
Deribit's JSON-RPC 2.0 API. It is intentionally small — just enough to read the
option chain and place/cancel paper-testnet orders — and mirrors the public-data
patterns from the lecture's `quant_desk/deribit.py`.

It is NOT exercised by the offline test suite (that uses the ReplayFeed +
SimBroker), so nothing here runs in `sim` mode. Secrets come ONLY from the
environment (`DERIBIT_CLIENT_ID` / `DERIBIT_CLIENT_SECRET`); the base url is
ALWAYS the testnet. We never place a real-money order.

Conventions (see botkit.types): premiums are in BTC, IV is a decimal, the
per-expiry forward is Deribit's `underlying_price`.
"""
from __future__ import annotations
import time
from typing import Optional

import httpx

from .types import Chain, OptionQuote, Order, Fill, PositionLeg


class DeribitClient:
    """Thin synchronous wrapper around Deribit's JSON-RPC 2.0 REST endpoint."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str = "https://test.deribit.com",
    ) -> None:
        # Guard rail for the assignment: never let anyone point this at mainnet.
        if "test.deribit.com" not in base_url:
            raise ValueError("base_url must be the Deribit TESTNET (test.deribit.com)")
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=10.0)
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    # --- low-level JSON-RPC plumbing -------------------------------------
    def _rpc(self, method: str, params: dict, private: bool = False) -> dict:
        """Call one JSON-RPC method and return its `result` (or raise)."""
        headers = {}
        if private:
            headers["Authorization"] = f"Bearer {self._ensure_token()}"
        resp = self._http.get(
            f"/api/v2/{method}", params=params, headers=headers
        )
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload and payload["error"]:
            raise RuntimeError(f"Deribit error on {method}: {payload['error']}")
        return payload["result"]

    # --- auth ------------------------------------------------------------
    def auth(self) -> str:
        """Fetch an OAuth bearer token via client_credentials. Returns the token."""
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "Missing DERIBIT_CLIENT_ID / DERIBIT_CLIENT_SECRET in the environment"
            )
        result = self._rpc(
            "public/auth",
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        self._token = result["access_token"]
        # Refresh a minute before the real expiry to be safe.
        self._token_expiry = time.time() + float(result.get("expires_in", 900)) - 60
        return self._token

    def _ensure_token(self) -> str:
        if self._token is None or time.time() >= self._token_expiry:
            self.auth()
        assert self._token is not None
        return self._token

    # --- public market data ---------------------------------------------
    def get_index(self, currency: str = "BTC") -> float:
        """Current spot index price in USD."""
        result = self._rpc("public/get_index_price", {"index_name": f"{currency.lower()}_usd"})
        return float(result["index_price"])

    def get_instruments(self, currency: str = "BTC", kind: str = "option") -> list[dict]:
        """All active instruments of `kind` for `currency`."""
        return self._rpc(
            "public/get_instruments",
            {"currency": currency, "kind": kind, "expired": "false"},
        )

    def get_ticker(self, instrument_name: str) -> dict:
        """Full ticker (mark, IV, greeks, forward) for one instrument."""
        return self._rpc("public/ticker", {"instrument_name": instrument_name})

    def get_chain(self, expiry_ts: int, currency: str = "BTC") -> Chain:
        """Build a Chain for one expiry by polling each instrument's ticker.

        IV is divided by 100 (Deribit quotes percent), the forward is taken from
        `underlying_price`, premiums stay in BTC.
        """
        instruments = [
            i for i in self.get_instruments(currency, "option")
            if int(i["expiration_timestamp"]) == int(expiry_ts)
        ]
        quotes: list[OptionQuote] = []
        forward = 0.0
        index = self.get_index(currency)
        ts = int(time.time() * 1000)
        for inst in instruments:
            t = self.get_ticker(inst["instrument_name"])
            g = t.get("greeks", {}) or {}
            forward = float(t.get("underlying_price", forward) or forward)
            index = float(t.get("index_price", index) or index)
            ts = int(t.get("timestamp", ts))
            quotes.append(
                OptionQuote(
                    instrument_name=inst["instrument_name"],
                    strike=float(inst["strike"]),
                    expiry_ts=int(inst["expiration_timestamp"]),
                    kind="C" if inst["option_type"] == "call" else "P",
                    bid=_f(t.get("best_bid_price")),
                    ask=_f(t.get("best_ask_price")),
                    mark=_f(t.get("mark_price")),
                    mark_iv=(_f(t.get("mark_iv")) or 0.0) / 100.0,
                    delta=_f(g.get("delta")),
                    gamma=_f(g.get("gamma")),
                    vega=_f(g.get("vega")),
                    theta=_f(g.get("theta")),
                    open_interest=_f(t.get("open_interest")),
                    volume=_f((t.get("stats") or {}).get("volume")),
                )
            )
        days = (int(expiry_ts) - ts) / 1000 / 86400
        return Chain(
            ts=ts, index=index, forward=forward or index,
            expiry_ts=int(expiry_ts), days_to_expiry=days, quotes=quotes,
        )

    # --- private trading -------------------------------------------------
    def place_order(self, order: Order) -> list[Fill]:
        """Send one order to the testnet and return the resulting fills."""
        method = "private/buy" if order.side == "buy" else "private/sell"
        params: dict = {
            "instrument_name": order.instrument_name,
            "amount": order.amount,
            "type": order.type,
            "label": order.label,
        }
        if order.type == "limit":
            params["price"] = order.price
        if order.reduce_only:
            params["reduce_only"] = "true"
        result = self._rpc(method, params, private=True)
        fills: list[Fill] = []
        for tr in result.get("trades", []):
            fills.append(
                Fill(
                    ts=int(tr.get("timestamp", time.time() * 1000)),
                    instrument_name=tr["instrument_name"],
                    side=tr["direction"],
                    amount=float(tr["amount"]),
                    price=float(tr["price"]),
                    fee=float(tr.get("fee", 0.0)),
                    order_label=order.label,
                )
            )
        return fills

    def cancel_all(self) -> None:
        """Cancel every open order on the account."""
        self._rpc("private/cancel_all", {}, private=True)

    def get_account_summary(self, currency: str = "BTC") -> dict:
        """Balance / equity / margin snapshot for the account."""
        return self._rpc(
            "private/get_account_summary", {"currency": currency, "extended": "true"},
            private=True,
        )

    def get_positions(self, currency: str = "BTC") -> list[PositionLeg]:
        """Open option positions as PositionLeg objects."""
        result = self._rpc(
            "private/get_positions", {"currency": currency, "kind": "option"},
            private=True,
        )
        legs: list[PositionLeg] = []
        for p in result:
            name = p["instrument_name"]
            # name looks like BTC-4JUL25-60000-C
            parts = name.split("-")
            strike = float(parts[2]) if len(parts) >= 4 else 0.0
            kind = "C" if name.endswith("C") else "P"
            legs.append(
                PositionLeg(
                    instrument_name=name,
                    size=float(p["size"]),  # already signed by Deribit
                    avg_price=float(p.get("average_price", 0.0)),
                    strike=strike,
                    kind=kind,
                    expiry_ts=0,
                    mark=_f(p.get("mark_price")),
                )
            )
        return legs

    def close(self) -> None:
        self._http.close()


def _f(x) -> Optional[float]:
    """Coerce a possibly-missing/None field to float (or None)."""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
