"""Client for Understat's undocumented league-data endpoint.

Primary source for team and player xG/xA/xGC: `teams[id].history` is
already at team level (h_a, xG, xGA, scored, missed, date per match), so
there's no per-player aggregation or transfer-misattribution risk the way
there is deriving this from the FPL API.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def fetch_league_data(season: str = "2026", refresh: bool = False) -> dict:
    """Returns {"teams": {...}, "players": [...], "dates": [...]}."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"understat_{season}.json"
    if not refresh and path.exists():
        return json.loads(path.read_text())
    url = f"https://understat.com/getLeagueData/EPL/{season}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://understat.com/league/EPL/{season}",
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    path.write_text(json.dumps(data))
    return data
