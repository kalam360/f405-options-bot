# F405 — Assignment: Build a BTC Weekly-Options Bot That *Survives*

**Type:** individual project · **Build:** ~2 weeks · **Live window:** 2 weekly cycles
(Friday → Friday → Friday) · **Grade:** out of 10 (see [RUBRIC.md](RUBRIC.md))

---

## 1. The scenario

You run a tiny options desk. Your capital is **fake BTC on Deribit testnet** (paper money —
never real funds). Your job is to write an **autonomous bot** that trades **BTC weekly
options** and is still standing after two weekly expiries. Not "made the most money in a
backtest" — **survived a real, moving, unfakeable market and grew its capital on a
risk-adjusted basis.**

The market is the judge. It does not care how clever your code looks; it cares whether you
respected your Greeks.

## 2. Why weekly options (and not spot, or monthlies)

- **Weekly options have the most theta and the most gamma.** Selling them feels like free
  money — premium decays fast in your favour — right up until the underlying jumps through
  your strike near expiry and the gamma turns that small short position into a large,
  fast-moving loss. One Friday can undo a month.
- **Short expiry = a fast feedback loop.** In a two-cycle live window you actually *see* an
  expiry happen to you. A monthly option would barely move; spot has no Greeks to manage.
- This is exactly the **gamma / theta / delta-hedging** trade-off from the lecture, lived in
  real time. The assignment forces you to manage it, not just define it.

## 3. You MAY use AI coding agents — as much as you want

Claude Code, Codex, opencode, Cursor — all allowed, all encouraged. This is not a
gotcha-by-plagiarism course. Use every tool you have.

Here is why that is safe for us and hard for you:

> An agent's default "make me a profitable options bot" answer is a **naked short
> straddle**. It prints money for a week, then a single weekly-expiry move **liquidates the
> account.** The agent will not save you, because it optimises for "looks profitable now,"
> not "survives the tail."

The graded skill is **steering the agent**: knowing that the naive answer is a time bomb,
asking for delta-hedging and hard risk limits, and **catching the quant mistakes the agent
makes** (wrong units, BTC-vs-USD premium, vega blowing past your limit, hedging the wrong
sign). You can only steer well if you actually understand the Greeks. The market + your
post-mortem make that understanding **unfakeable**, with or without AI.

## 4. What you build

On the provided `botkit` framework, implement **two classes** in `strategies/template.py`:

- **`MyStrategy(Strategy)`** — your alpha. Each tick it sees the front-weekly option `Chain`
  and your `AccountState`, and returns the `Order`s it wants. Decision-only: same inputs →
  same orders (so it is testable in sim).
- **`MyRisk(RiskManager)`** — your survival. `vet()` can resize or drop any order before it
  reaches the broker; `should_halt()` is your **kill-switch** that flattens the book and
  stops trading when things go wrong (drawdown, margin, vega/delta out of bounds).

You do **not** write the exchange client, feed, broker, portfolio, journal, runner, or
scorer — those are provided. See the repo map in [../README.md](../README.md).

## 5. The rules (these are graded)

1. **Options only.** Your edge must come from options and their Greeks. You may trade the
   perpetual/futures **only to hedge delta** — no pure directional spot bets as the strategy.
2. **Autonomous.** The bot decides and places its own orders via the runner. No manual
   clicking, no discretionary trades.
3. **Mandatory risk controls.** You must set explicit `RiskLimits`, enforce them in `vet()`,
   and implement a working **kill-switch** in `should_halt()`. The provided defaults are
   deliberately loose — tightening and defending them is part of the work.
4. **Sim before live.** Develop and stabilise in offline sim mode first. `uv run pytest`
   must stay green.
5. **No manual overrides during the live window.** Once the live window opens, the bot runs
   **unattended**. You may not log in and trade by hand, tweak positions, or restart it into
   a different strategy mid-cycle. (You may keep it *running* — fix a crash, not a position.)
6. **Testnet only.** Base URL is always `https://test.deribit.com`. Never place a real order.

## 6. Timeline

- **Build (~2 weeks):** implement and test in sim. Iterate with your AI agent. Tighten risk.
- **Live window (2 weekly cycles):** the bot runs unattended on Deribit testnet across two
  consecutive weekly expiries (**Friday → Friday → Friday**). The class leaderboard tracks
  everyone's equity and risk-adjusted score live.
- **Between cycle 1 and cycle 2:** you may review and adjust *before* cycle 2 opens — and you
  must write up **what you changed and why** in the post-mortem.

## 7. Deliverables

Submit via **GitHub Classroom** (your per-student repo). Autograding runs `pytest` + a sim
run + the scorer on every push.

1. **The repo** — your code **and its commit history** (we read the history; commit often).
2. **AI-agent evidence** — your transcripts/logs **and** the `CLAUDE.md` / `AGENTS.md` you
   wrote to steer your agent.
3. **A written POST-MORTEM** (the heart of the grade) covering:
   - your strategy and **why it should work**, grounded in vol / skew / term-structure / Greeks;
   - **where the agent got the quant wrong** and how you caught it;
   - **what you changed between cycle 1 and cycle 2**, and why.
4. **A read-only Deribit testnet API key** registered for the **live leaderboard** (read-only
   = graders can see your equity but can never trade your account).

## 8. How it's graded

Out of **10**, with **live, risk-adjusted performance** and **survival** weighted most, and a
big share for the **post-mortem + agent workflow**. A blow-up (liquidation, or equity falling
below 25% of start) **caps live performance at 0** no matter how good the run looked before.
There is a small, capped leaderboard bonus for top-quartile **risk-adjusted** results.

Full bands and the evidence that earns each one: **[RUBRIC.md](RUBRIC.md)**.

## 9. Getting started

Read **[../README.md](../README.md)**, run the quickstart, then run all three baselines in
sim and read their code. When you understand *why* `naive_short_straddle` blows up and
*why* `delta_hedged_vol_seller` survives, you understand the assignment. Now beat it.
