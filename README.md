# f405-options-bot — autonomous BTC weekly-options paper-trading bot

A **starter kit** for the IBA **F405 Derivatives** assignment. You will build a small
trading bot that sells/buys **BTC weekly options on Deribit testnet** (paper money), and
that must **survive a live market** for two weekly cycles without blowing up.

The hard part is not the code — an AI coding agent can write most of it. The hard part is
**steering that agent** so the bot understands its Greeks and does not get liquidated on the
first big Friday move. That understanding is the graded skill.

> New here? Read **[docs/ASSIGNMENT.md](docs/ASSIGNMENT.md)** for the full brief and
> **[docs/RUBRIC.md](docs/RUBRIC.md)** for exactly how you are graded.

---

## What you actually build

You implement **two classes** on a framework that is already written for you:

| You write | File | Job |
|---|---|---|
| `Strategy` | `strategies/template.py` | Your **alpha** — looks at the option chain + your account and returns the orders it wants. |
| `RiskManager` | `strategies/template.py` | Your **survival** — limits, hedging, and a kill-switch that flatten you before you blow up. |

Everything else (the exchange client, the market feed, the broker, the portfolio
accounting, the trade journal, the run loop, the scorer) is **provided**. You import it; you
do not rewrite it.

---

## Quickstart (sim mode — no account, no keys, no network)

Sim mode replays a captured option chain and evolves the price with a seeded random walk, so
it is **deterministic and fully offline**. Develop here first; only go live once your bot
survives sim.

```bash
# 0. install uv once (https://astral.sh/uv). then, from the repo root:
uv sync                       # create the venv and install everything

# 1. run the test suite (pricing math, sim smoke test, scorer)
uv run pytest

# 2. run a baseline bot in sim — the one you must beat
#    (the runner takes a dotted module:Class — open the baseline file to see its
#     exact Strategy/Risk class names, then plug them in below)
uv run python -m botkit.runner \
    --config config.example.yaml \
    --strategy strategies.baselines.delta_hedged_vol_seller:DeltaHedgedVolSeller \
    --risk     strategies.baselines.delta_hedged_vol_seller:HedgedRisk

# 3. score the run you just produced
uv run python score.py runs/latest      # prints + writes runs/latest/score.json

# 4. (optional) see WHY each baseline wins or loses
uv run jupyter lab notebooks/01_baselines_walkthrough.ipynb
```

Step 2 leaves a complete **journal** in `runs/latest/` (`trades.csv`, `equity.csv`,
`meta.json`). Step 3 turns that journal into a risk-adjusted score — the same scorer the
autograder runs.

### Run YOUR bot in sim

Edit `strategies/template.py`, then point the runner at it:

```bash
uv run python -m botkit.runner \
    --config config.example.yaml \
    --strategy strategies.template:MyStrategy \
    --risk     strategies.template:MyRisk
uv run python score.py runs/latest
```

### The three baselines (run them, read them, understand them)

| Baseline | What it does | What happens |
|---|---|---|
| `naive_short_straddle` | Sells the ATM weekly straddle, **no risk layer**. | Prints theta for a few days, then **gets liquidated** on one weekly jump. This is the trap. |
| `buy_and_hold_call` | Buys one ATM weekly call and holds. | Bleeds **theta** to zero most weeks. |
| `delta_hedged_vol_seller` | Sells the straddle **and re-hedges to ~0 net delta every tick**. | Survives. **This is the bot to beat.** |

---

## Going live (Deribit **testnet** — still paper money)

Only after your bot survives in sim. Live mode trades on `https://test.deribit.com` — a
sandbox with fake BTC. **It is never real money, and this kit never points anywhere else.**

1. **Create a testnet account** at <https://test.deribit.com> (separate from the real
   Deribit site). Confirm your email and log in.
2. **Generate API keys**: *Account → API*. Create **two** keys:
   - a **trading key** (read + trade) — your bot uses this to place paper orders;
   - a **read-only key** — you register this for the **leaderboard** so graders can read
     your equity but can never trade your account.
3. **Set your secrets** — copy `.env.example` to `.env` and paste your trading key:
   ```bash
   cp .env.example .env
   # then edit .env:
   #   DERIBIT_CLIENT_ID=your_client_id
   #   DERIBIT_CLIENT_SECRET=your_client_secret
   ```
   `.env` is git-ignored. **Never commit a key.** Secrets are read from the environment
   only, never from the YAML config.
4. **Fund the account**: testnet usually credits you with fake BTC automatically; if not,
   use the testnet faucet in the UI.
5. **Run live**:
   ```bash
   BOT_MODE=live uv run python -m botkit.runner \
       --config config.example.yaml \
       --strategy strategies.template:MyStrategy \
       --risk     strategies.template:MyRisk
   ```
   For the live window the bot must run **unattended** (e.g. on a small VPS or a `tmux`
   session). **No manual trading during the live window** — see the assignment rules.

---

## Repo map

```
botkit/                 # the provided framework — import it, don't rewrite it
  types.py              # pinned data types (Chain, OptionQuote, Order, Fill, AccountState, Greeks ...)
  pricing.py            # tested Black-Scholes price / Greeks / implied vol
  strategy.py           # the Strategy interface you implement
  risk.py               # the RiskManager interface + RiskLimits you implement
  config.py             # Config (loads config.yaml + env secrets)
  deribit.py            # Deribit testnet client (auth, chain, orders, account)
  feed.py               # market feed: LiveFeed (testnet) / ReplayFeed (offline sim)
  broker.py             # order execution: LiveBroker / SimBroker (paper fills)
  portfolio.py          # positions, mark-to-market equity, net Greeks
  journal.py            # writes trades.csv / equity.csv / meta.json  (fixed schema)
  runner.py             # the event loop: `python -m botkit.runner`
strategies/
  template.py           # >>> YOU WRITE HERE <<< MyStrategy + MyRisk
  baselines/            # the three reference bots (incl. the one to beat)
notebooks/              # quickstart + baselines walkthrough
score.py                # journal -> risk-adjusted score.json (grading)
tests/                  # pytest: pricing, sim smoke test, scorer
docs/ASSIGNMENT.md      # the full brief
docs/RUBRIC.md          # the /10 and what earns each band
config.example.yaml     # run settings (mode, tick cadence, sim seed, risk limits)
.env.example            # where your testnet keys go (copy to .env)
leaderboard/            # the live class leaderboard (deploy is optional, instructor-run)
AGENTS.md / CLAUDE.md   # how to point an AI coding agent at this repo
```

## Where to put your work

- **Strategy + RiskManager:** `strategies/template.py` (`MyStrategy`, `MyRisk`).
- **Run settings:** copy/edit `config.example.yaml` (tick cadence, sim length, risk limits).
- **Don't touch:** anything in `botkit/` (especially `types.py` and the `journal.py`
  schema — the autograder depends on it).

## Golden rules (the framework assumes these — so should your bot)

- **Vol/IV is a decimal** (0.65 = 65%), **time-to-expiry is in years**, **size is signed
  contracts** (+long / −short, 1 contract = 1 BTC).
- Deribit quotes option premiums **in BTC**. Convert to USD with that expiry's **forward**
  (`chain.forward` / `underlying_price`), **not spot** — this matches the lecture notebook.
- **Secrets only from the environment.** Base URL is always `https://test.deribit.com`.
- **Sim before live.** If it isn't green in `uv run pytest` and stable in sim, it isn't ready.

## Submission (GitHub Classroom)

Push to your per-student repo. Autograding runs `pytest` + a sim run + the scorer on every
push. Final deliverables: the repo (with commit history), your AI-agent transcripts and the
`CLAUDE.md`/`AGENTS.md` you wrote, a written **post-mortem**, and your **read-only** testnet
key for the leaderboard. Full details in **[docs/ASSIGNMENT.md](docs/ASSIGNMENT.md)**.
