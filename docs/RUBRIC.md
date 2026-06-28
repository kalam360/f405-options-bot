# F405 — Grading Rubric (/10)

Your bot is graded on five things. **Live, risk-adjusted performance** and **survival** carry
the most weight, but the **post-mortem and your AI-agent workflow** are where you prove you
actually understand the quant — and they are worth as much as raw performance. Total **10**,
plus a small capped leaderboard bonus.

| # | Criterion | Points |
|---|---|---:|
| 1 | Live performance (risk-adjusted) | 3.0 |
| 2 | Risk management & survival | 2.0 |
| 3 | Engineering | 2.0 |
| 4 | Strategy & quant rationale | 1.5 |
| 5 | AI-agent workflow & post-mortem | 1.5 |
| — | **Subtotal** | **10.0** |
| + | Leaderboard bonus (capped) | +0.5 |

---

## How performance is measured (read this first)

The scorer (`score.py`) reads your run's `equity.csv` and computes:

- **`total_return`** = end equity / start equity − 1.
- **`max_drawdown`** = the largest peak-to-trough fall in equity over the run.
- **`risk_adjusted = total_return / max(max_drawdown, 0.02)`** — return **per unit of pain**.
  The `0.02` floor stops a near-zero drawdown from producing an absurd ratio.
- **`blew_up`** = `True` if the account was **liquidated** *or* equity ever fell below **25%
  of where it started**.

**Why risk-adjusted, not raw return?** A naked short straddle can post a huge raw return for
a week — and then a single Friday move erases it. Dividing by drawdown rewards the bot that
makes steady money **without** taking the account to the edge. That is the whole point of the
course: surviving the tail beats looking rich on Tuesday.

**The blow-up rule:** if `blew_up` is true, **line 1 (live performance) is 0**, regardless of
how good the run looked beforehand. A liquidated desk is out of business. There is no partial
credit for "but it was up 80% before it died."

---

## Line 1 — Live performance, risk-adjusted (3.0)

Scored from your **live** testnet run over the two weekly cycles, against the provided
`delta_hedged_vol_seller` baseline. The scorer emits `score_0_3`:

| Band | Evidence | Points |
|---|---|---:|
| Blew up | `blew_up = True` (liquidated or equity < 25% of start) | **0** |
| Survived, weak | Survived but risk-adjusted **below** the delta-hedged baseline | **0.5 – 1.5** |
| At baseline | Risk-adjusted **≈** the delta-hedged baseline | **~2.0** |
| Above baseline | Clearly beats the baseline on risk-adjusted return | **2.0 – 2.7** |
| Top of class | Best-in-class risk-adjusted return, no scary drawdowns | **2.7 – 3.0** |

The exact `risk_adjusted → score_0_3` mapping is implemented and documented in `score.py`,
and is the **same** code the autograder runs — there are no hidden criteria.

## Line 2 — Risk management & survival (2.0)

Did your risk layer actually do its job? Evidence comes from your code and your journal.

- **2.0** — Explicit, defended `RiskLimits`; `vet()` measurably resizes/blocks orders;
  `should_halt()` fired (or provably would fire) on drawdown/margin; net delta and net vega
  stayed inside your stated bounds in `equity.csv`. **Did not blow up.**
- **1.0 – 1.5** — Real limits and a kill-switch, but with gaps (e.g. vega allowed to drift,
  hedging lagged the move).
- **0.0 – 0.5** — Limits cosmetic or absent; survival was luck. (A blow-up lands here.)

## Line 3 — Engineering (2.0)

- **2.0** — Bot ran **unattended for the full live window**; clean use of the provided
  interfaces (no edits to `botkit/`); the journal schema intact; meaningful logging;
  `uv run pytest` green, including your own tests.
- **1.0 – 1.5** — Ran with minor babysitting; some tests; mostly clean.
- **0.0 – 0.5** — Crashed and stayed down; broke the journal schema; fought the framework.

## Line 4 — Strategy & quant rationale (1.5)

A written argument for **why your edge should exist**, grounded in the lecture: implied vs
realised vol, the **skew**, **term structure**, and which **Greeks** you are harvesting vs
hedging. Full marks reason in Greeks ("I'm short vega and theta-positive, hedging gamma by
re-delta-ing each tick, capped tails with a wing"); low marks assert "it makes money" with no
mechanism.

## Line 5 — AI-agent workflow & post-mortem (1.5)

This is where AI use becomes a *strength*. Evidence: your transcripts/commits, the
`CLAUDE.md`/`AGENTS.md` you wrote, and the post-mortem.

- **1.5** — Transcripts/commits clearly show you **steering** the agent (asking for hedging
  and limits, not just "make money"); you **caught specific quant mistakes** the agent made
  (a unit error, BTC-vs-USD premium, wrong hedge sign, vega over limit) and document the fix;
  the post-mortem honestly explains your strategy and **what changed between cycle 1 and 2**.
- **0.5 – 1.0** — Some steering and reflection, but thin on caught mistakes or the cycle-to-
  cycle change.
- **0.0** — No transcripts, or a post-mortem that just narrates the result.

## Leaderboard bonus (+0.5, capped)

Top-quartile of the class on **risk-adjusted** score (not raw return) earns up to **+0.5**,
and the bonus **cannot push your total above 10**. It rewards genuine risk-adjusted skill, not
a lucky directional punt — and a blow-up forfeits it.

---

### One-line summary

**Survive first, compound steadily second, and prove in your post-mortem that you — not the
agent — understood the Greeks.** That is how you score in this course.
