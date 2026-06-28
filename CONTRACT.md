# BUILD CONTRACT — f405-options-bot

This is the internal spec for the people (agents) building this starter kit. It is
the single source of truth: implement these signatures and schemas EXACTLY. The
pinned interfaces already exist in `botkit/{types,strategy,risk,config}.py` and
`botkit/pricing.py` — import from them, never redefine them.

The repo is a **starter kit students fork** (via GitHub Classroom). Students implement
`Strategy` + `RiskManager`; everything else here is provided. The bot trades **BTC
weekly options on Deribit testnet**. It must run **fully offline in `sim` mode** (no
keys, no network) so it is testable in CI and by graders.

## Golden rules
- vol/IV is decimal; T is years; position size is signed contracts (1 = 1 BTC).
- Deribit quotes premiums in BTC; convert to USD with the per-expiry **forward**
  (`underlying_price`), matching the lecture notebook (NOT spot).
- Secrets only from env (`DERIBIT_CLIENT_ID/SECRET`); base url is always
  `https://test.deribit.com`. Never place a real-money order.
- Everything importable as `botkit.<module>`; tests via `uv run pytest`.

## File tree (build to this)
```
botkit/
  types.py strategy.py risk.py config.py pricing.py __init__.py   # DONE (pinned)
  deribit.py     # Deribit testnet REST+WS client (auth, get chain, place/cancel, account)
  feed.py        # MarketFeed: LiveFeed (WS) + ReplayFeed (offline). yields Chain objects
  broker.py      # Broker: LiveBroker (real testnet orders) + SimBroker (paper fills)
  portfolio.py   # Portfolio: positions, mark-to-market equity, net Greeks (uses pricing)
  journal.py     # Journal: append trades.csv + equity.csv in the FIXED schema below
  runner.py      # the event loop tying it all together; `python -m botkit.runner`
strategies/
  template.py            # MyStrategy/MyRisk stubs students fill in (TODOs)
  baselines/
    naive_short_straddle.py     # sells the ATM weekly straddle, no hedge  (the BOMB)
    buy_and_hold_call.py        # buys one ATM weekly call, holds          (theta bleed)
    delta_hedged_vol_seller.py  # sells straddle + delta-hedges each tick   (the one to beat)
notebooks/
  00_quickstart.ipynb           # connect/sim, see a chain, place a paper trade
  01_baselines_walkthrough.ipynb# run all 3 baselines in sim, show why each wins/loses
score.py            # CLI: read a run's journal -> risk-adjusted score JSON  (grading)
tests/              # pytest: pricing sanity, sim runner smoke test, score on fixture
docs/ASSIGNMENT.md docs/RUBRIC.md            # student-facing brief + rubric
README.md AGENTS.md CLAUDE.md                # setup + AI-agent guidance
config.example.yaml .env.example
leaderboard/        # web (Next.js/Vercel) + poller (GH Actions + Turso)
.github/workflows/autograde.yml .github/classroom/autograding.json
```

## Module responsibilities + key signatures

### botkit/deribit.py  (live path; not unit-tested against network)
`class DeribitClient(client_id, client_secret, base_url="https://test.deribit.com")`
- `auth()`, `get_index(currency="BTC") -> float`, `get_instruments(currency, kind="option")`
- `get_chain(expiry_ts) -> Chain` (build OptionQuote list w/ mark_iv/100, greeks, forward=underlying_price)
- `place_order(Order) -> list[Fill]`, `cancel_all()`, `get_account_summary() -> dict`, `get_positions() -> list[PositionLeg]`
- Reuse the public-data patterns from the lecture repo's `quant_desk/deribit.py`. Use httpx; WS optional for v1 (REST polling is acceptable at tick_seconds cadence).

### botkit/feed.py
`class MarketFeed(Protocol): def chains() -> Iterator[Chain]`
- `LiveFeed(client, cfg)`: polls the **front weekly** expiry every `tick_seconds`.
- `ReplayFeed(cfg)`: offline. Loads `cfg.sim_snapshot`, picks the nearest-to-7-day
  expiry as "the weekly", then synthesizes a `sim_days`-long path by evolving the
  index with seeded GBM (`sim_seed`) and re-pricing each quote's mark from its
  `mark_iv` via `pricing.bs_price` on the forward; yields one Chain per tick. This
  is what makes sim deterministic and offline. Front-weekly selector =
  expiry whose days_to_expiry is closest to 7 (configurable).

### botkit/broker.py
`class Broker(Protocol): def execute(orders, chain) -> list[Fill]; def sync(account)`
- `SimBroker`: fills market orders at mark ± half-spread (or a small slippage),
  applies a fee (Deribit taker ≈ 0.0003 BTC/contract, capped), updates the Portfolio.
- `LiveBroker(client)`: routes Order -> client.place_order, returns real Fills,
  refreshes positions/equity from the account summary.

### botkit/portfolio.py
`class Portfolio(start_cash_btc, pricing)` with:
- `apply(fill)`, `mark(chain)` -> updates marks, `state(chain) -> AccountState`
  (equity_usd, cash, net Greeks via `pricing.greeks` on each leg & the forward,
  pnl realized/unrealized, margin_util estimate, liquidated flag when equity<=0).
- Net delta in BTC; net vega in USD/1.00 vol; theta USD/yr — match types.Greeks.

### botkit/journal.py  (THE GRADING CONTRACT — fixed schema)
`class Journal(dir)` writes two CSVs (append, header once):
- `trades.csv`: `ts,iso,instrument,side,amount,price_btc,price_usd,fee_btc,strategy,label`
- `equity.csv`: `ts,iso,equity_usd,cash_btc,index,forward,net_delta,net_vega_usd,net_theta_usd,margin_util,realized_usd,unrealized_usd,liquidated`
- one `equity.csv` row per tick; one `trades.csv` row per fill. Also write
  `meta.json` (strategy name, mode, start/end ts, start_equity_usd).

### botkit/runner.py
`def run(cfg: Config, strategy: Strategy, risk: RiskManager) -> dict` loop:
```
feed = LiveFeed|ReplayFeed ; broker = Live|Sim ; pf = Portfolio ; jr = Journal
strategy.on_start(state)
for chain in feed.chains():
    pf.mark(chain); state = pf.state(chain); jr.equity(state)
    if risk.should_halt(state): flatten(); break
    orders = strategy.on_chain(chain, state)
    orders = risk.vet(orders, chain, state)
    for f in broker.execute(orders, chain): pf.apply(f); jr.trade(f, strategy.name); strategy.on_fill(f)
return summary(meta)
```
`python -m botkit.runner --config config.example.yaml --strategy strategies.template:MyStrategy --risk strategies.template:MyRisk`
(dotted `module:Class` loader). Default mode sim. Must run end-to-end offline and
leave a complete journal in `cfg.journal_dir`.

### score.py  (grading — must be deterministic)
`python score.py runs/latest` -> prints + writes `score.json`:
- read equity.csv. Compute: `total_return`, `max_drawdown`, `sharpe` (per-tick
  returns, annualized by ticks/yr), **risk_adjusted = total_return / max(max_drawdown, 0.02)**,
  `blew_up` (liquidated flag OR equity ever < 25% of start), `cycles` (per-weekly-expiry P&L).
- Final `score_0_3` mapping for rubric line 1: blew_up -> 0; else scale
  risk_adjusted vs the delta-hedged baseline (>= baseline -> ~2, top -> 3). Document the mapping.
- Pure stdlib + pandas; no network. A fixture journal under tests/fixtures must score.

## Strategy/RiskManager (students implement; provide stubs + baselines)
- `strategies/template.py`: `class MyStrategy(Strategy)` + `class MyRisk(RiskManager)`
  with clear TODOs and a couple of hints (use chain.nearest_delta, watch net vega).
- Baselines implement the same interfaces and are the benchmarks. `naive_short_straddle`
  must have NO risk layer (uses default loose RiskLimits) so it visibly blows up on a move.
  `delta_hedged_vol_seller` re-hedges to ~0 net delta each tick — the target to beat.

## Docs (student-facing — write these from the assignment design)
- `docs/ASSIGNMENT.md`: the brief. Scenario, why weekly options, allowed to use AI
  agents freely, what to build (Strategy+RiskManager), the rules (autonomous bot, no
  manual overrides in the live window, options-only, mandatory risk limits), timeline
  (~2-week build + **2 weekly cycles live, Fri->Fri**), deliverables (repo + agent
  transcripts + post-mortem), and how it's graded (point to RUBRIC.md). Tone: clear
  for BBA students with light coding background.
- `docs/RUBRIC.md`: the /10 (performance 3 risk-adjusted+blowup=0; risk/survival 2;
  engineering 2; quant rationale 1.5; AI-agent workflow & post-mortem 1.5; +0.5
  leaderboard bonus capped). Explain each band and what evidence earns it.
- `README.md`: quickstart — uv sync, run sim, run a baseline, run score, then the
  live testnet steps (create testnet account at test.deribit.com, make API keys,
  set .env, run live). `AGENTS.md`/`CLAUDE.md`: how a coding agent should work in
  this repo (run `uv run pytest`, the interfaces to implement, sim-first, the
  schema it must not break) — help the agent be productive without handing over alpha.

## Leaderboard (leaderboard/)
- `poller/poll.py`: for each registered student (roster + **read-only** Deribit
  testnet key), call account summary, compute equity + risk-adjusted score + blew_up,
  upsert into Turso (libSQL). Schema in `leaderboard/schema.sql`
  (students, equity_snapshots, scores). Read-only keys can't trade -> safe.
- `.github/workflows/poll-leaderboard.yml`: cron every 15 min -> run poller (secrets
  from repo secrets). `web/`: Next.js app (App Router) reading Turso, showing live
  ranking, equity sparkline, 💀 for blew_up, sorted by risk-adjusted score. Deploy
  to Vercel (free). `leaderboard/README.md`: exact deploy steps (Turso create db,
  Vercel env vars, GH secrets). This sub-project can't be live-tested here; make it
  structurally complete with copy-paste deploy instructions.

## CI / Classroom
- `.github/workflows/autograde.yml`: uv sync -> pytest -> run sim runner with the
  delta-hedged baseline -> score it -> assert it produced a valid score.json (so a
  student's push is checked end-to-end).
- `.github/classroom/autograding.json`: GitHub Classroom autograding tests calling
  the above (pytest + a smoke "bot runs in sim" test), with point values.

Keep every file focused and commented for a student audience. When done, the repo
must: `uv sync` clean, `uv run pytest` green, `uv run python -m botkit.runner` (sim)
produce a journal, and `uv run python score.py runs/latest` print a score.
