"""Upcoming fixtures per team, from the FPL API's own fixture list.

This is the one source that correctly reflects blank gameweeks (a team
absent from an `event`) and double gameweeks (a team appearing twice in
one `event`) -- Understat's match dates carry no gameweek number.
"""
from __future__ import annotations


def build_fixtures_by_team(fpl_fixtures: list[dict], bootstrap: dict) -> dict[str, list[dict]]:
    short_by_id = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    by_team: dict[str, list[dict]] = {short: [] for short in short_by_id.values()}

    for f in fpl_fixtures:
        if f["finished"] or f["event"] is None:
            continue
        home, away = short_by_id[f["team_h"]], short_by_id[f["team_a"]]
        by_team[home].append({"gw": f["event"], "opp": away, "venue": "H"})
        by_team[away].append({"gw": f["event"], "opp": home, "venue": "A"})

    for short in by_team:
        by_team[short].sort(key=lambda r: r["gw"])
    return by_team
