"""Command-line entrypoint: `python -m fpl_predictor refresh` (or `build`).

refresh -- re-fetch live data (ignoring any cache) and regenerate
           output/dashboard.html.
build   -- regenerate output/dashboard.html from whatever is already cached,
           without hitting the network. Useful for iterating on the template.
check   -- decide whether the live site needs a redeploy: a newer gameweek
           has finished, FPL has confirmed its results and (when xG comes
           from Understat) Understat has caught up. Prints the reason and
           writes deploy=true|false to $GITHUB_OUTPUT when set. If a data
           source errors, it only exits non-zero (failing the run, which
           notifies) once the live site has gone stale; until then it
           just warns, since most outages are over by the next run.

Team xG comes from the FPL API or Understat, per config.XG_SOURCE.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
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
# Understat catching up (when used) and a missed twice-daily check run.
STALE_GRACE = timedelta(hours=36)
_LIVE_GW_RE = re.compile(r"after Gameweek (\d+)")
_LIVE_STALE_RE = re.compile(r"const STALE_CHECK = (.*?);")


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


def _live_page() -> str:
    """The deployed dashboard's HTML, or "" if it can't be fetched."""
    try:
        resp = requests.get(SITE_URL, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return ""
    return resp.text


def _live_gameweek(html: str) -> int:
    """The gameweek the deployed dashboard shows, or 0 if it can't be read
    (which forces a redeploy)."""
    m = _LIVE_GW_RE.search(html)
    return int(m.group(1)) if m else 0


def _live_stale_after(html: str) -> datetime | None:
    """When the deployed dashboard starts showing its "out of date" modal,
    or None if that can't be read off it."""
    m = _LIVE_STALE_RE.search(html)
    if not m:
        return None
    try:
        stale = json.loads(m.group(1))
        return datetime.fromisoformat(stale["after"].replace("Z", "+00:00"))
    except (ValueError, TypeError, KeyError):
        return None


def check() -> bool:
    bootstrap = fpl_client.fetch_bootstrap(refresh=True)
    fpl_fixtures = fpl_client.fetch_fixtures(refresh=True)

    finished_gw = _last_finished_gameweek(bootstrap)
    live_gw = _live_gameweek(_live_page())
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


def _set_deploy_output(deploy: bool) -> None:
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as fh:
            fh.write(f"deploy={str(deploy).lower()}\n")


def _check_failed() -> int:
    """check raised -- almost always a data source being down or changed.
    Most outages are over by the next run, so only fail the run (which is
    what sends a notification) once the live site has gone stale, i.e. its
    visitors are seeing the "out of date" modal. Until then, warn."""
    traceback.print_exc()
    stale_after = _live_stale_after(_live_page())
    if stale_after is not None and datetime.now(timezone.utc) < stale_after:
        print(
            "::warning::check failed (traceback above); not failing the run "
            f"unless it's still failing when the live site goes stale at "
            f"{stale_after:%Y-%m-%d %H:%M} UTC"
        )
        _set_deploy_output(False)
        return 0
    if stale_after is None:
        print("::error::check failed (traceback above) and the live site's stale deadline couldn't be read")
    else:
        print("::error::check failed (traceback above) and the live site is out of date")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fpl_predictor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("refresh", help="re-fetch live data and regenerate the dashboard")
    sub.add_parser("build", help="regenerate the dashboard from cached data only")
    sub.add_parser("check", help="decide whether the live site needs a redeploy")
    args = parser.parse_args(argv)

    if args.command == "check":
        try:
            deploy = check()
        except Exception:
            return _check_failed()
        _set_deploy_output(deploy)
        return 0

    path = run(refresh=(args.command == "refresh"))
    print(f"Wrote {path} (xG source: {config.XG_SOURCE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
