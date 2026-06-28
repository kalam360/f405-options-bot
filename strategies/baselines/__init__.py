"""Baseline strategies — the benchmarks the assignment is graded against.

These are deliberately simple, *reference* strategies. They are NOT the answer
you should submit; they exist so you can see, in sim, how three classic options
postures behave on the same price path:

  * ``naive_short_straddle``    — sell vol, no risk layer  -> blows up (the bomb).
  * ``buy_and_hold_call``       — long one ATM call, hold  -> bleeds theta.
  * ``delta_hedged_vol_seller`` — sell vol + hedge delta   -> the one to beat.

Each module exposes a ``Strategy`` and a ``RiskManager`` so it can be run by the
runner directly, e.g.::

    uv run python -m botkit.runner --config config.example.yaml \\
        --strategy strategies.baselines.delta_hedged_vol_seller:DeltaHedgedVolSeller \\
        --risk     strategies.baselines.delta_hedged_vol_seller:HedgedRisk \\
        --journal-dir runs/hedged
"""
