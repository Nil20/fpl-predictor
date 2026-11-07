"""Command-line entrypoint: `python -m fpl_predictor refresh` (or `build`).

refresh -- re-fetch live data (ignoring any cache) and regenerate
           output/dashboard.html.
build   -- regenerate output/dashboard.html from whatever is already cached,
           without hitting the network. Useful for iterating on the template.
check   -- decide whether the live site needs a redeploy: a newer gameweek
           has finished, FPL has confirmed its results and (when xG comes
           from Understat) Understat has caught up. Prints the reason and
           writes deploy=true|false to $GITHUB_OUTPUT when set.

Team xG comes from the FPL API or Understat, per config.XG_SOURCE.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from . import analysis, config, fpl_client, team_xg, understat_client
from .fixtures import build_fixtures_by_team
from .render import render_dashboard

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "output" / "dashboard.html"
SEASON = "2026"
SEASON_LABEL = "2026/27"
SITE_URL = "https://fpl-predictor-nine.vercel.app"
# How long after the next gameweek's last kickoff the page starts warning
# that it's stale. Covers the match itself, FPL confirming bonus points,
# Understat catching up (when used) and a few missed 3-hourly check runs.
STALE_GRACE = timedelta(hours=36)
_LIVE_GW_RE = re.compile(r"after Gameweek (\d+)")


def _last_finished_gameweek(bootstrap: dict) -> int:
    """The header reads 'after Gameweek N' -- N should be the last one
    actually played, not FPL's 'current' event (which flips to the
    upcoming gameweek as soon as its deadline passes, even before a
    ball's been kicked)."""
    finished = [e["id"] for e in bootstrap["events"] if e["finished"]]
    return max(finished, default=0)


def _stale_check(fpl_fixtures: list[dict], current_gw: int) -> dict | None:
    """When the page should start warning that its data is out of date:
    STALE_GRACE after the last kickoff of the gameweek after the one it
    shows. None if that gameweek has no scheduled kickoffs (end of season)."""
    next_gw = current_gw + 1
    kickoffs = [
        datetime.fromisoformat(f["kickoff_time"].replace("Z", "+00:00"))
        for f in fpl_fixtures
        if f["event"] == next_gw and f["kickoff_time"]
    ]
    if not kickoffs:
        return None
    after = max(kickoffs) + STALE_GRACE
    return {"gw": next_gw, "after": after.strftime("%Y-%m-%dT%H:%M:%SZ")}


def _live_gameweek() -> int:
    """The gameweek the deployed dashboard shows, or 0 if it can't be read
    (which forces a redeploy)."""
    try:
        resp = requests.get(SITE_URL, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return 0
    m = _LIVE_GW_RE.search(resp.text)
    return int(m.group(1)) if m else 0


def check() -> bool:
    bootstrap = fpl_client.fetch_bootstrap(refresh=True)
    fpl_fixtures = fpl_client.fetch_fixtures(refresh=True)

    finished_gw = _last_finished_gameweek(bootstrap)
    live_gw = _live_gameweek()
    if finished_gw <= live_gw:
        print(f"Live site already shows Gameweek {live_gw}; nothing to do.")
        return False

    # A fixture's `finished` flips once FPL has confirmed its bonus points,
    # by which time its players' match histories (and xG) are final.
    unconfirmed = sum(
        1 for f in fpl_fixtures
        if f["event"] is not None and f["event"] <= finished_gw and not f["finished"]
    )
    if unconfirmed:
        print(
            f"Gameweek {finished_gw} has been played but FPL hasn't confirmed "
            f"{unconfirmed} of its results yet; waiting."
        )
        return False

    if config.XG_SOURCE == "understat":
        understat_data = understat_client.fetch_league_data(season=SEASON, refresh=True)
        fpl_results = sum(f["finished"] for f in fpl_fixtures)
        understat_results = sum(d["isResult"] for d in understat_data["dates"])
        if understat_results < fpl_results:
            print(
                f"Gameweek {finished_gw} finished but Understat has {understat_results} "
                f"of {fpl_results} results; waiting for it to catch up."
            )
            return False
    print(f"Gameweek {finished_gw} finished (live site shows {live_gw}); redeploying.")
    return True


def _team_matches(bootstrap: dict, fpl_fixtures: list[dict], refresh: bool) -> dict[str, list[dict]]:
    if config.XG_SOURCE == "understat":
        understat_data = understat_client.fetch_league_data(season=SEASON, refresh=refresh)
        return team_xg.from_understat(understat_data)
    histories = fpl_client.fetch_player_histories(bootstrap, refresh=refresh)
    team_matches, mismatches = team_xg.from_fpl(fpl_fixtures, histories, bootstrap)
    for m in mismatches:
        print(f"warning: {m} (that match's xG may be undercounted)", file=sys.stderr)
    return team_matches


def run(refresh: bool) -> Path:
    bootstrap = fpl_client.fetch_bootstrap(refresh=refresh)
    fpl_fixtures = fpl_client.fetch_fixtures(refresh=refresh)
    team_matches = _team_matches(bootstrap, fpl_fixtures, refresh)

    league_table = analysis.compute_league_table(team_matches, bootstrap)
    home_away = analysis.compute_home_away_split(team_matches, bootstrap)
    fixtures_by_team = build_fixtures_by_team(fpl_fixtures, bootstrap)
    current_gw = _last_finished_gameweek(bootstrap)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = render_dashboard(
        league_table=league_table,
        home_away=home_away,
        fixtures_by_team=fixtures_by_team,
        current_gw=current_gw,
        season_label=SEASON_LABEL,
        generated_at=generated_at,
        stale_check=_stale_check(fpl_fixtures, current_gw),
        source_note=team_xg.SOURCE_NOTES[config.XG_SOURCE],
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html)
    return OUTPUT_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fpl_predictor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("refresh", help="re-fetch live data and regenerate the dashboard")
    sub.add_parser("build", help="regenerate the dashboard from cached data only")
    sub.add_parser("check", help="decide whether the live site needs a redeploy")
    args = parser.parse_args(argv)

    if args.command == "check":
        deploy = check()
        if output := os.environ.get("GITHUB_OUTPUT"):
            with open(output, "a") as fh:
                fh.write(f"deploy={str(deploy).lower()}\n")
        return 0

    path = run(refresh=(args.command == "refresh"))
    print(f"Wrote {path} (xG source: {config.XG_SOURCE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
