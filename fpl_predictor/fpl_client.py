"""Thin client for the official FPL API: gameweek/fixture calendar and prices.

Team-level xG/xGC comes from Understat instead (see understat_client) -- the
FPL API only exposes that per-player, and aggregating it correctly across a
team requires reconciling mid-season transfers, which Understat's team-level
match history sidesteps entirely.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

BASE = "https://fantasy.premierleague.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0"}
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def _cached_get(url: str, cache_name: str, refresh: bool) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / cache_name
    if not refresh and path.exists():
        return json.loads(path.read_text())
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    path.write_text(json.dumps(data))
    return data


def fetch_bootstrap(refresh: bool = False) -> dict:
    """Players (prices, ownership), teams, and the gameweek calendar."""
    return _cached_get(f"{BASE}/bootstrap-static/", "fpl_bootstrap.json", refresh)


def fetch_fixtures(refresh: bool = False) -> list[dict]:
    """Full fixture list, each tagged with an `event` (gameweek) number --
    the only source that correctly reflects blank and double gameweeks."""
    return _cached_get(f"{BASE}/fixtures/", "fpl_fixtures.json", refresh)
