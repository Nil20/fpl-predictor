"""Turns raw Understat + FPL data into the league table and home/away split.

Both are plain aggregations over Understat's team-level match history --
no network calls, unit-testable against small hand-built fixtures.
"""
from __future__ import annotations

from .team_map import UNDERSTAT_TO_FPL


def _fpl_name_lookup(bootstrap: dict) -> dict[str, str]:
    return {t["short_name"]: t["name"] for t in bootstrap["teams"]}


def compute_league_table(understat_data: dict, bootstrap: dict) -> list[dict]:
    """One row per team: goals, points, and season-to-date xG/xGC, derived
    entirely from Understat's per-match team history (already cross-checked
    against FPL's own fixture results during design -- see the design spec's
    appendix)."""
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
            "Pts": pts,
        })
    rows.sort(key=lambda r: (-r["Pts"], -r["GD"]))
    return rows


def compute_home_away_split(understat_data: dict, bootstrap: dict) -> list[dict]:
    """Per-team xG/xGC, separated by venue -- a team's home form can look
    nothing like its away form."""
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
        rows.append({
            "team": name_by_short[short],
            "short": short,
            "homeG": home_games,
            "homeXG": round(home_xg, 2),
            "homeXGC": round(home_xgc, 2),
            "homeXGD": round(home_xg - home_xgc, 2),
            "awayG": away_games,
            "awayXG": round(away_xg, 2),
            "awayXGC": round(away_xgc, 2),
            "awayXGD": round(away_xg - away_xgc, 2),
        })
    rows.sort(key=lambda r: r["short"])
    return rows
