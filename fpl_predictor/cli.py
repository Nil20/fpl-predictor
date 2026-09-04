"""Command-line entrypoint: `python -m fpl_predictor refresh` (or `build`).

refresh -- re-fetch from Understat + FPL (ignoring any cache) and regenerate
           output/dashboard.html.
build   -- regenerate output/dashboard.html from whatever is already cached,
           without hitting the network. Useful for iterating on the template.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import analysis, fpl_client, understat_client
from .fixtures import build_fixtures_by_team
from .render import render_dashboard

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "output" / "dashboard.html"
SEASON = "2026"
SEASON_LABEL = "2026/27"


def _last_finished_gameweek(bootstrap: dict) -> int:
    """The header reads 'after Gameweek N' -- N should be the last one
    actually played, not FPL's 'current' event (which flips to the
    upcoming gameweek as soon as its deadline passes, even before a
    ball's been kicked)."""
    finished = [e["id"] for e in bootstrap["events"] if e["finished"]]
    return max(finished, default=0)


def run(refresh: bool) -> Path:
    bootstrap = fpl_client.fetch_bootstrap(refresh=refresh)
    fpl_fixtures = fpl_client.fetch_fixtures(refresh=refresh)
    understat_data = understat_client.fetch_league_data(season=SEASON, refresh=refresh)

    league_table = analysis.compute_league_table(understat_data, bootstrap)
    home_away = analysis.compute_home_away_split(understat_data, bootstrap)
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
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html)
    return OUTPUT_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fpl_predictor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("refresh", help="re-fetch live data and regenerate the dashboard")
    sub.add_parser("build", help="regenerate the dashboard from cached data only")
    args = parser.parse_args(argv)

    path = run(refresh=(args.command == "refresh"))
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
