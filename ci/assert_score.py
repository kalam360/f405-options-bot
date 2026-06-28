"""CI guard: assert a run's score.json is structurally valid.

Used by .github/workflows/autograde.yml after the sim run is scored. Exits
non-zero (failing the build) if the file is missing keys or has bad types, so
a broken scorer or journal can never silently pass autograding.

    uv run python ci/assert_score.py runs/ci/score.json
"""
from __future__ import annotations

import json
import sys

# The grading contract: score.py must emit at least these fields (see score.py
# and docs/RUBRIC.md). Keep this list in sync with the documented schema.
REQUIRED_KEYS = [
    "total_return",
    "max_drawdown",
    "sharpe",
    "risk_adjusted",
    "blew_up",
    "score_0_3",
]


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "runs/latest/score.json"

    try:
        with open(path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        print(f"FAIL: {path} not found — score.py did not write it", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"FAIL: {path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        print(f"FAIL: {path} missing keys: {missing}", file=sys.stderr)
        return 1

    if not isinstance(data["blew_up"], bool):
        print("FAIL: blew_up must be a bool", file=sys.stderr)
        return 1

    score = data["score_0_3"]
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        print("FAIL: score_0_3 must be numeric", file=sys.stderr)
        return 1
    if not 0 <= score <= 3:
        print(f"FAIL: score_0_3 out of range [0, 3]: {score}", file=sys.stderr)
        return 1

    print(f"OK: {path} is valid (score_0_3={score}, blew_up={data['blew_up']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
