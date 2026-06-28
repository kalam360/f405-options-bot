# AGENTS.md — guidance for AI coding agents (Codex, opencode, Cursor, …)

This is the vendor-neutral twin of [`CLAUDE.md`](CLAUDE.md). Same rules apply to **any**
coding agent. If your tool reads `CLAUDE.md`, read that; otherwise read this. **You are
encouraged to use AI agents on this assignment** — but you, the student, are graded on
steering them, so edit this file to encode the strategy you choose. Submitting it is part of
the deliverable.

## The task

Help build an **autonomous BTC weekly-options paper-trading bot** on **Deribit testnet** for
IBA F405. Read `docs/ASSIGNMENT.md` and `CONTRACT.md` first.

## Scope — implement only two classes

In **`strategies/template.py`**:
- `MyStrategy(Strategy)` → `on_chain(chain, account) -> list[Order]` (pure, decision-only).
- `MyRisk(RiskManager)` → `vet(orders, chain, account)` and `should_halt(account)` (kill-switch).

**Do not modify `botkit/`** — it is the provided, tested framework the autograder relies on.

## Run / test (uv only — never pip or poetry)

```bash
uv sync
uv run pytest                                   # must stay green
uv run python -m botkit.runner --config config.example.yaml \
    --strategy strategies.template:MyStrategy --risk strategies.template:MyRisk
uv run python score.py runs/latest
```

Sim mode is offline + deterministic. **Stabilise in sim before going live.** Live mode
(`BOT_MODE=live`, keys in `.env`) only ever uses `https://test.deribit.com`.

## Golden rules (match these or the numbers are wrong)

- Vol/IV is a **decimal** (0.65 = 65%); time-to-expiry in **years**; size in **signed
  contracts** (1 = 1 BTC).
- Premiums are in **BTC** — convert to USD with the expiry **forward** (`chain.forward`),
  **not** spot (`chain.index`). Most common bug.
- Reuse `botkit.pricing` (`bs_price`, `greeks`, `implied_vol`); don't re-derive Black-Scholes.
- Secrets only from the environment; never commit `.env` or hard-code a key.

## Don't break the journal schema (the grading contract)

The runner writes `runs/<run>/trades.csv`, `equity.csv`, `meta.json` via `botkit/journal.py`.
Columns and order are fixed — see `CLAUDE.md`. Your code must not write or alter these files.

## Survival is the point — never ship the naive short straddle

The default "profitable options bot" is a **naked short straddle**: it prints theta, then a
weekly-expiry jump liquidates it (short gamma). The repo ships it as a baseline so you can
watch it die. A surviving bot **delta-hedges** toward ~0 net delta each tick, **caps net vega
and gross size** in `vet()`, and has a **kill-switch** that flattens on drawdown/margin before
liquidation. Prefer capping the tail over the last basis point of premium — the grader divides
return by drawdown.

## Done means

`uv sync` clean · `uv run pytest` green · sim run leaves a full journal · `score.py` reports
`blew_up = False` with a healthy risk-adjusted score · risk limits + kill-switch visibly
active. Clean, commented code and frequent, explainable commits (the history is graded).
