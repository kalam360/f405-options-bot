# Instructor Grading Guide — scoring the `/10` in practice

This is the operational companion to [`RUBRIC.md`](RUBRIC.md). The rubric defines the bands;
this doc tells you **which command to run and which file to read** to award each one, plus a
short **viva script** to confirm the student — not the agent — understands the Greeks.

The autograder's 6+4 is only a CI health check. The real grade is the five rubric lines below
(10.0) plus the capped leaderboard bonus (+0.5). Grade each student repo after the live window.

> **Setup once per grading session.** Clone the student's final repo (their per-student
> Classroom repo, `f405-bot-<handle>`), check out their last commit *before/at the live-window
> close*, and `uv sync`. You will run their code in `sim` and read their journal + post-mortem.

---

## Quick map: rubric line → what you do

| Rubric line | Pts | How you score it |
|---|---:|---|
| 1 — Live performance (risk-adjusted) | 3.0 | Run `score.py` on their **live** run journal → `score_0_3`; cross-check the leaderboard rank |
| 2 — Risk management & survival | 2.0 | Read `equity.csv` (vega/delta bounds, kill-switch), read `MyRisk` code |
| 3 — Engineering | 2.0 | `uv run pytest`; check `botkit/` untouched + journal schema intact; read commit history |
| 4 — Strategy & quant rationale | 1.5 | Read the post-mortem's strategy section; confirm with viva |
| 5 — AI-agent workflow & post-mortem | 1.5 | Read transcripts + `CLAUDE.md`/`AGENTS.md` + post-mortem's "caught mistakes" + cycle-1→2 change |
| Bonus | +0.5 | Top-quartile risk-adjusted on the leaderboard, capped, forfeited on blow-up |

---

## Line 1 — Live performance, risk-adjusted (3.0)

Score this from the student's **live testnet run**, not a sim run. Their live journal should be
committed under `runs/` (or they hand you the `equity.csv`).

```bash
uv run python score.py runs/<their-live-run>     # writes/prints score.json
```

Read these keys from `score.json`:
- **`blew_up`** — if `True` (liquidated, or equity ever < 25% of start), **Line 1 = 0**. Hard stop.
  No partial credit for "it was up 80% before it died."
- **`risk_adjusted`** = `total_return / max(max_drawdown, 0.02)` — the headline number.
- **`score_0_3`** — the scorer's mapping of `risk_adjusted` vs the `delta_hedged_vol_seller`
  baseline. This *is* your Line 1 unless you see a reason to override.

Map to bands (same as `RUBRIC.md`): blew up → **0**; survived but below baseline → **0.5–1.5**;
≈ baseline → **~2.0**; clearly above → **2.0–2.7**; best-in-class with no scary drawdowns →
**2.7–3.0**. Sanity-check against the **leaderboard** ranking, which runs the identical math
(`leaderboard/poller/poll.py`); the two should agree.

> To recompute the baseline yourself for comparison:
> `uv run python -m botkit.runner --config config.example.yaml --mode sim --journal-dir runs/baseline --strategy strategies.baselines.delta_hedged_vol_seller:DeltaHedgedVolSeller --risk strategies.baselines.delta_hedged_vol_seller:HedgedRisk && uv run python score.py runs/baseline`

## Line 2 — Risk management & survival (2.0)

Evidence is in `equity.csv` and in their `MyRisk`:

- Open `equity.csv` and check **`net_vega_usd`** and **`net_delta`** stayed inside the bounds
  the student claims in the post-mortem. Vega drifting steadily wider = the limit was cosmetic.
- Look for the **kill-switch firing**: a drawdown/margin breach followed by the book flattening
  (positions → 0, equity stabilising) **before** liquidation. `should_halt()` that never could
  have fired is not a kill-switch.
- Read `strategies/template.py` → `MyRisk.vet()`: does it **measurably resize/block** orders
  (vega, net delta, gross contracts, margin), or just pass them through?
- **2.0** = explicit defended limits, `vet()` visibly acts, `should_halt()` fired or provably
  would, stayed in bounds, did not blow up. **1.0–1.5** = real but gappy. **0–0.5** = cosmetic
  or absent (a blow-up lands here).

## Line 3 — Engineering (2.0)

```bash
uv run pytest                          # must be green, including the student's own tests
git -C <repo> log --oneline --stat     # read the commit history
git -C <repo> diff <template-base> -- botkit/    # MUST be empty: botkit/ is off-limits
```

- **`botkit/` unchanged** and the **journal schema intact** (columns/order of `trades.csv` and
  `equity.csv` exactly as in `CLAUDE.md`). Editing `botkit/` or writing the journal from
  strategy code is a real deduction — the autograder depends on that contract.
- Ran **unattended for the full live window** (ask for/inspect logs; gaps that are crash-fixes
  are fine, strategy-swaps mid-cycle are not — see rule 5 in `ASSIGNMENT.md`).
- Meaningful **commit history** (commit-often, explainable messages) and their **own tests**.
- **2.0** = clean, unattended, tests green. **1.0–1.5** = minor babysitting / thin tests.
  **0–0.5** = crashed and stayed down, or broke the schema.

## Line 4 — Strategy & quant rationale (1.5)

Read the **post-mortem's strategy section**. Full marks reason **in Greeks** — e.g. "short
vega, theta-positive, gamma-hedged by re-delta-ing each tick, tail capped with a long wing,"
with a view on implied-vs-realised vol, the **skew**, or **term structure**. Low marks assert
"it makes money" with no mechanism. Confirm it is *their* understanding with the viva below.

## Line 5 — AI-agent workflow & post-mortem (1.5)

This is where AI use becomes a strength. Evidence: their **transcripts/commits**, the
`CLAUDE.md`/`AGENTS.md` **they wrote** (the shipped ones are templates — did they make them
theirs?), and the post-mortem.

- **1.5** — transcripts clearly show **steering** (asking for hedging + limits, not "make
  money"); they **caught specific quant mistakes** the agent made (a unit error, BTC-vs-USD
  premium, wrong hedge sign, vega over limit) and document the fix; the post-mortem honestly
  explains the strategy **and what changed between cycle 1 and cycle 2**.
- **0.5–1.0** — some steering/reflection, thin on caught mistakes or the cycle-to-cycle change.
- **0.0** — no transcripts, or a post-mortem that just narrates the result.

## Leaderboard bonus (+0.5, capped)

Top-quartile of the class on **risk-adjusted** score (read directly off the live leaderboard).
Capped at +0.5, **cannot push the total above 10**, and **forfeited by any blow-up**.

---

## Viva script (5 minutes, confirms it's the student not the agent)

Do this for anyone scoring high on Lines 4–5, or anyone whose post-mortem reads like the agent
wrote it. You are checking *understanding*, not memorised code. Good answers are in Greeks and
units; hand-waving "the agent did it" is the tell.

1. **Units / robustness:** "Recompute your edge with **r = 8%** (or T longer by 3 days). Which
   way does your option value move and why?" — They should reason about discounting / carry and
   know `botkit.pricing` takes **decimal** vol and **years**, not percent/days.
2. **Their own book:** "Your `equity.csv` shows **net vega = X** at \<timestamp\>. Why that sign
   and size? What in the chain made it move?" — Confirms they read their own Greeks, not just
   shipped a baseline.
3. **The hedge:** "When BTC moved \<this much\> near expiry, what did `MyRisk`/your hedge do, and
   why did short **gamma** make that urgent?" — The core gamma/theta/delta trade-off.
4. **BTC vs USD:** "Where do you convert a BTC premium to USD — spot or the forward — and what
   breaks if you use the wrong one?" — The single most common quant bug; answer must be **forward**.
5. **Steering:** "Show me one place the agent gave you a wrong answer and how you caught it." —
   Direct evidence for Line 5. A real example (with the commit/transcript) earns the marks.

Award full Lines 4–5 only when the answers are theirs. If the student cannot explain their own
journal numbers, mark Lines 4–5 down regardless of how polished the write-up looks — that is
exactly the unfakeable check the course is built around.
