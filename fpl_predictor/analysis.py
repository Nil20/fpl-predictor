"""Turns raw Understat + FPL data into the league table and home/away split.

Both are plain aggregations over Understat's team-level match history --
no network calls, unit-testable against small hand-built fixtures.

Per-match (rate) figures are computed alongside the season totals: once
blank/double gameweeks start happening, teams stop having played the same
number of matches, and raw totals stop being comparable -- a team with 3
away games will out-total one with 1 even at a lower per-match rate. The
fixture ticker bands on the per-match rate for exactly this reason.
"""
from __future__ import annotations

from .team_map import UNDERSTAT_TO_FPL


def _fpl_name_lookup(bootstrap: dict) -> dict[str, str]:
    return {t["short_name"]: t["name"] for t in bootstrap["teams"]}


def _per_match(total: float, played: int) -> float:
    return round(total / played, 2) if played else 0.0


def compute_league_table(understat_data: dict, bootstrap: dict) -> list[dict]:
    """One row per team: goals, points, and season-to-date xG/xGC (plus
    per-match rates), derived entirely from Understat's per-match team
    history (already cross-checked against FPL's own fixture results
    during design -- see the design spec's appendix)."""
    name_by_short = _fpl_name_lookup(bootstrap)
    rows = []
    for team in understat_data["teams"].values():
        short = UNDERSTAT_TO_FPL[team["title"]]
        played = gf = ga = pts = 0
        xg = xgc = 0.0
        for h in team["history"]:
            played += 1
            gf += h["scored"]
            ga += h["missed"]
            pts += h["pts"]
            xg += h["xG"]
            xgc += h["xGA"]
        xg_pm = _per_match(xg, played)
        xgc_pm = _per_match(xgc, played)
        rows.append({
            "team": name_by_short[short],
            "short": short,
            "played": played,
            "GF": gf,
            "GA": ga,
            "GD": gf - ga,
            "xG": round(xg, 2),
            "xGC": round(xgc, 2),
            "xGD": round(xg - xgc, 2),
            "xGPerMatch": xg_pm,
            "xGCPerMatch": xgc_pm,
            "xGDPerMatch": round(xg_pm - xgc_pm, 2),
            "Pts": pts,
        })
    rows.sort(key=lambda r: (-r["Pts"], -r["GD"]))
    return rows


def compute_home_away_split(understat_data: dict, bootstrap: dict) -> list[dict]:
    """Per-team xG/xGC, separated by venue (plus per-match rates) -- a
    team's home form can look nothing like its away form."""
    name_by_short = _fpl_name_lookup(bootstrap)
    rows = []
    for team in understat_data["teams"].values():
        short = UNDERSTAT_TO_FPL[team["title"]]
        home_xg = home_xgc = away_xg = away_xgc = 0.0
        home_games = away_games = 0
        for h in team["history"]:
            if h["h_a"] == "h":
                home_games += 1
                home_xg += h["xG"]
                home_xgc += h["xGA"]
            else:
                away_games += 1
                away_xg += h["xG"]
                away_xgc += h["xGA"]
        home_xg_pm = _per_match(home_xg, home_games)
        home_xgc_pm = _per_match(home_xgc, home_games)
        away_xg_pm = _per_match(away_xg, away_games)
        away_xgc_pm = _per_match(away_xgc, away_games)
        rows.append({
            "team": name_by_short[short],
            "short": short,
            "homeG": home_games,
            "homeXG": round(home_xg, 2),
            "homeXGC": round(home_xgc, 2),
            "homeXGD": round(home_xg - home_xgc, 2),
            "homeXGPerMatch": home_xg_pm,
            "homeXGCPerMatch": home_xgc_pm,
            "homeXGDPerMatch": round(home_xg_pm - home_xgc_pm, 2),
            "awayG": away_games,
            "awayXG": round(away_xg, 2),
            "awayXGC": round(away_xgc, 2),
            "awayXGD": round(away_xg - away_xgc, 2),
            "awayXGPerMatch": away_xg_pm,
            "awayXGCPerMatch": away_xgc_pm,
            "awayXGDPerMatch": round(away_xg_pm - away_xgc_pm, 2),
        })
    rows.sort(key=lambda r: r["short"])
    return rows
