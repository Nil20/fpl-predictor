"""Settings you might want to flip without touching the rest of the code."""
from __future__ import annotations

import os

# Where team xG/xGC comes from:
#   "fpl"       -- the official FPL API: each team's xG is the sum of its
#                  players' Opta xG per match, xGC is the opponent's xG.
#   "understat" -- Understat's team-level match xG.
# The XG_SOURCE environment variable overrides this. The GitHub workflows
# read it from the repository variable XG_SOURCE (Settings > Secrets and
# variables > Actions > Variables), so the live site can be flipped without
# a code change.
XG_SOURCE = os.environ.get("XG_SOURCE") or "fpl"

XG_SOURCES = ("fpl", "understat")
if XG_SOURCE not in XG_SOURCES:
    raise SystemExit(f"XG_SOURCE must be one of {XG_SOURCES}, got {XG_SOURCE!r}")
