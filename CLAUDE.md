# CLAUDE.md — guidance for a coding agent working in this repo

> This is a **template** for *your* agent instructions. You are encouraged to use AI coding
> agents (Claude Code, Codex, opencode, …) freely on this assignment — but **you** are graded
> on steering them well. Edit this file to encode the strategy *you* decide on. Submitting it
> is part of the deliverable.

You are helping a student build an **autonomous BTC weekly-options paper-trading bot** on
**Deribit testnet** for the IBA F405 course. Read `docs/ASSIGNMENT.md` and `CONTRACT.md` for
the full spec before changing code.

## What the student implements (and all you should touch)

Only two classes, both in **`strategies/template.py`**:

- `MyStrategy(Strategy)` — implement `on_chain(chain, account) -> list[Order]`
  (and optionally `on_start`, `on_fill`). Decision-only and pure: same inputs → same orders.
- `MyRisk(RiskManager)` — implement `vet(orders, chain, account) -> list[Order]` and
  `should_halt(account) -> bool` (the kill-switch).

Run settings live in a copy of `config.example.yaml`. **Do not touch `botkit/`** — it is the
provided, tested framework, and the autograder depends on it.

## How to run things (use uv — never pip/poetry)

```bash
uv sync                       # install deps
uv run pytest                 # MUST stay green; add your own tests under tests/
uv run python -m botkit.runner --config config.example.yaml \
    --strategy strategies.template:MyStrategy --risk strategies.template:MyRisk
uv run python score.py runs/latest      # risk-adjusted score from the journal
```

Sim mode is **offline and deterministic** (seeded replay). Develop and stabilise there
**before** ever going live. Live mode (`BOT_MODE=live`) needs testnet keys in `.env` and
**only** ever talks to `https://test.deribit.com`.

## Golden rules — get these wrong and the bot is silently broken

The framework assumes these conventions everywhere. Match them or your numbers are garbage:

- **Vol / IV is a DECIMAL** (0.65 = 65%), not a percent. `OptionQuote.mark_iv` is already
  divided by 100.
- **Time-to-expiry is in YEARS** when you call `botkit.pricing` (`days / 365`).
- **Size is signed contracts**: `+` long, `−` short; 1 contract = 1 BTC.
- **Premiums are in BTC.** Deribit quotes option prices in coin. Convert to USD with that
  expiry's **forward** (`chain.forward` / `underlying_price`), **NOT spot** (`chain.index`).
  This matches the lecture notebook. Mixing these up is the single most common quant bug.
- **Reuse `botkit.pricing`** (`bs_price`, `greeks`, `implied_vol`) — it is tested. Do not
  hand-roll Black-Scholes.
- **Secrets only from the environment** (`DERIBIT_CLIENT_ID/SECRET`). Never read keys from
  YAML, never hard-code them, never commit `.env`.

## The journal schema is a CONTRACT — never break it

`botkit/journal.py` writes the files the grader reads. Do not change the columns or order:

- `trades.csv`: `ts,iso,instrument,side,amount,price_btc,price_usd,fee_btc,strategy,label`
- `equity.csv`: `ts,iso,equity_usd,cash_btc,index,forward,net_delta,net_vega_usd,net_theta_usd,margin_util,realized_usd,unrealized_usd,liquidated`

Your strategy/risk code must **not** write these files itself — the runner does. If you need
extra telemetry, log it separately.

## Survival is the assignment — do NOT ship the naive answer

The default "make a profitable options bot" design is a **naked short straddle**. It harvests
theta for a few days and then **gets liquidated** on one weekly-expiry jump, because its
short gamma turns a price move into an accelerating loss right at expiry. The repo ships this
as `strategies/baselines/naive_short_straddle.py` **specifically so you can watch it blow
up.** Do not propose it as the solution.

A bot that survives must, at minimum:

- **manage delta** — re-hedge toward ~0 net delta as the underlying moves (gamma scalping),
  like `strategies/baselines/delta_hedged_vol_seller.py`, the baseline to beat;
- **bound vega and gross size** in `MyRisk.vet()` — refuse orders that would push net vega,
  net delta, gross contracts, or margin past the limits;
- **have a real kill-switch** in `should_halt()` that flattens on a drawdown / margin breach
  **before** liquidation, not after.

When in doubt, prefer **capping the tail** (e.g. buying a cheap wing) over squeezing one more
basis point of premium. The grader divides return by drawdown; a smaller drawdown is worth
more than a bigger headline return.

## Definition of done

`uv sync` clean · `uv run pytest` green · sim run produces a full journal in `runs/latest/` ·
`score.py runs/latest` reports `blew_up = False` with a healthy risk-adjusted score · risk
limits and kill-switch demonstrably active in the journal. Keep code clean and commented —
engineering and the commit history are graded. Commit often with clear messages; the student
must be able to explain every change in the post-mortem.
