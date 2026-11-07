"""Team-level match history (xG, xGC, goals, points), from either source.

Both builders return {team short_name: [one row per finished match]} with
the same keys (h_a, xG, xGA, scored, missed, pts, date), which is all
analysis.py reads; config.XG_SOURCE picks which one runs.

from_understat: Understat's history is already per team per match, so this
only maps Understat's team names onto FPL's.

from_fpl: FPL publishes Opta xG per player per match (element-summary
history). A team's xG in a match is the sum of its players' xG -- every
shot belongs to exactly one player, so this adds up with no double
counting -- and its xGC is simply the opponent's xG. Two pitfalls hit in an earlier attempt at this
(see the design spec's appendix) are avoided:

- A player's side in each match comes from that row's `was_home` and the
  fixture's home/away teams, not from the club they're at now, so
  mid-season transfers are credited to the right team.
- xGC is never read off players' `expected_goals_conceded`, which doesn't
  replicate cleanly across a team's players (substitutes, two keepers).

Goals and points come from the fixture's own score. Player goals (plus the
opponent's own goals) are summed too, purely as a completeness check: if
they don't reproduce the score, some player rows are missing and that
match's xG is undercounted.
"""
from __future__ import annotations

from .team_map import UNDERSTAT_TO_FPL

# Footer text on the dashboard, per source (HTML).
SOURCE_NOTES = {
    "fpl": (
        "official FPL API &middot; team xG is the sum of its players&rsquo; Opta xG "
        "each match, xGC is the opponent&rsquo;s xG &middot; goals and points from "
        "FPL match results."
    ),
    "understat": (
        "Understat (xG, xGC) &middot; goals and points computed from Understat "
        "match results, cross-checked against the FPL API."
    ),
}


def from_understat(understat_data: dict) -> dict[str, list[dict]]:
    return {
        UNDERSTAT_TO_FPL[team["title"]]: team["history"]
        for team in understat_data["teams"].values()
    }


def _points(scored: int, missed: int) -> int:
    if scored > missed:
        return 3
    return 1 if scored == missed else 0


def from_fpl(
    fpl_fixtures: list[dict], histories: dict[str, list[dict]], bootstrap: dict
) -> tuple[dict[str, list[dict]], list[str]]:
    """Returns ({team short_name: [one row per finished match, oldest
    first]}, [a description of each match whose player rows don't add up
    to its score])."""
    short_by_id = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    finished = {f["id"]: f for f in fpl_fixtures if f["finished"]}

    xg = {fid: {"h": 0.0, "a": 0.0} for fid in finished}
    goals = {fid: {"h": 0, "a": 0} for fid in finished}
    for rows in histories.values():
        for row in rows:
            fid = row["fixture"]
            if fid not in finished:
                continue
            side, other = ("h", "a") if row["was_home"] else ("a", "h")
            xg[fid][side] += float(row["expected_goals"])
            goals[fid][side] += row["goals_scored"]
            goals[fid][other] += row["own_goals"]

    by_team: dict[str, list[dict]] = {short: [] for short in short_by_id.values()}
    mismatches = []
    for fid, f in sorted(finished.items(), key=lambda kv: kv[1]["kickoff_time"]):
        home, away = short_by_id[f["team_h"]], short_by_id[f["team_a"]]
        home_score, away_score = f["team_h_score"], f["team_a_score"]
        if (goals[fid]["h"], goals[fid]["a"]) != (home_score, away_score):
            mismatches.append(
                f"GW{f['event']} {home} {home_score}-{away_score} {away}: "
                f"player rows add up to {goals[fid]['h']}-{goals[fid]['a']}"
            )
        for team, h_a, scored, missed in (
            (home, "h", home_score, away_score),
            (away, "a", away_score, home_score),
        ):
            opp_h_a = "a" if h_a == "h" else "h"
            by_team[team].append({
                "fixture": fid,
                "gw": f["event"],
                "date": f["kickoff_time"],
                "h_a": h_a,
                "xG": round(xg[fid][h_a], 2),
                "xGA": round(xg[fid][opp_h_a], 2),
                "scored": scored,
                "missed": missed,
                "pts": _points(scored, missed),
            })
    return by_team, mismatches
