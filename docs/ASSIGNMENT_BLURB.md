# Assignment description (copy-paste into the GitHub Classroom assignment field)

> Paste the block below into the Classroom assignment **description**. It is deliberately
> short — the full brief lives in `docs/ASSIGNMENT.md` and the rubric in `docs/RUBRIC.md`
> inside the starter repo.

---

**Build a BTC weekly-options bot that survives.** You run a tiny options desk with fake BTC
on Deribit **testnet** (paper money — never real funds). On the provided `botkit` framework
you implement two classes in `strategies/template.py`: **`MyStrategy`** (your edge — what
options to trade each tick) and **`MyRisk`** (your survival — order limits and a kill-switch).
Everything else — exchange client, market feed, broker, portfolio, journal, scorer — is given.
The goal is not "biggest backtest return"; it is to be **still standing, on a risk-adjusted
basis, after two real weekly expiries.**

**You may use AI coding agents (Claude Code, Codex, Cursor, opencode) as much as you want —
this is encouraged, not policed.** The catch: an agent's default "make a profitable options
bot" answer is a naked short straddle that prints money for a week and then gets liquidated on
one weekly-expiry jump. The graded skill is **steering** the agent toward delta-hedging and
hard risk limits, and **catching the quant mistakes it makes** (unit errors, BTC-vs-USD
premium, wrong hedge sign, vega over limit). The market and your post-mortem make that
understanding unfakeable.

**Live window + leaderboard.** After a ~2-week build phase (develop offline in deterministic
`sim` mode, keep `uv run pytest` green), your bot runs **unattended** on Deribit testnet across
**two weekly cycles (Friday → Friday → Friday)**. A live class **leaderboard** ranks everyone
by **risk-adjusted** return, with a 💀 badge for any bot that blows up (liquidated or equity
below 25% of start). A blow-up caps live performance at **0**, no matter how good it looked
before. Deliverables: your repo + commit history, your AI-agent transcripts, a read-only
testnet API key for the leaderboard, and a **post-mortem** explaining your strategy, the quant
mistakes you caught, and what you changed between cycle 1 and cycle 2.

**Start here:** read the repo `README.md`, run the quickstart, then run all three baselines in
`sim` and read their code. When you understand *why* `naive_short_straddle` blows up and *why*
`delta_hedged_vol_seller` survives, you understand the assignment. Now beat the hedged
baseline. Full brief: `docs/ASSIGNMENT.md` · Grading: `docs/RUBRIC.md`.
