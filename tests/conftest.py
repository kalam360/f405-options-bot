"""Make the repo root importable so tests can `import score` and
`import strategies.template` (the `botkit` package is installed by uv, but the
top-level `score.py` module and the `strategies` package live at the repo root).
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
