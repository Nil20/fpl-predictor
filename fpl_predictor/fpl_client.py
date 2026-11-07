"""Thin client for the official FPL API: gameweek/fixture calendar, prices,
and each player's per-match history (the source of team xG when
config.XG_SOURCE is "fpl", see team_xg.from_fpl).
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://fantasy.premierleague.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0"}
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"

# Only what team_xg needs from each element-summary history row; the full
# rows are ~40 fields and there are ~500 players.
_HISTORY_FIELDS = ("fixture", "was_home", "minutes", "expected_goals", "goals_scored", "own_goals")
_WORKERS = 8


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


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=_WORKERS))
    return session


def fetch_player_histories(bootstrap: dict, refresh: bool = False) -> dict[str, list[dict]]:
    """{player id: [one row per match they played this season]}, trimmed to
    _HISTORY_FIELDS. One element-summary call per player who has played
    any minutes (~500), fetched in parallel."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / "fpl_player_histories.json"
    if not refresh and path.exists():
        return json.loads(path.read_text())

    session = _session()

    def fetch(player_id: int) -> tuple[str, list[dict]]:
        resp = session.get(f"{BASE}/element-summary/{player_id}/", timeout=20)
        resp.raise_for_status()
        rows = [
            {k: row[k] for k in _HISTORY_FIELDS}
            for row in resp.json()["history"]
            if row["minutes"] > 0
        ]
        return str(player_id), rows

    player_ids = [p["id"] for p in bootstrap["elements"] if p["minutes"] > 0]
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        histories = dict(pool.map(fetch, player_ids))

    path.write_text(json.dumps(histories))
    return histories
