"""Renders the dashboard template with fresh data.

The template (templates/dashboard_template.html) is the exact page design
validated interactively earlier -- this just swaps its embedded sample data
and header text for freshly computed values from analysis.py / fixtures.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent / "templates" / "dashboard_template.html"

_DATA_RE = re.compile(
    r"const DATA = \[.*?\]\.map\(r => \(\{\.\.\.r, xGD: Math\.round\(\(r\.xG - r\.xGC\) \* 100\) / 100\}\)\);",
    re.DOTALL,
)
_HOME_AWAY_RE = re.compile(
    r"const HOME_AWAY_RAW = \[.*?\];\s*"
    r"const HOME_AWAY = HOME_AWAY_RAW\.map\(r => \(\{.*?\}\)\);",
    re.DOTALL,
)
_FIXTURES_RE = re.compile(r"const FIXTURES_BY_TEAM = \{.*?\};", re.DOTALL)
_EYEBROW_RE = re.compile(
    r'<span class="eyebrow">Premier League &middot; [^<]*</span>'
)
_ASOF_RE = re.compile(
    r'document\.getElementById\("asof"\)\.textContent =\s*'
    r'"Generated " \+ new Date\(\)\.toISOString\(\)\.slice\(0, 10\);',
    re.DOTALL,
)


def render_dashboard(
    league_table: list[dict],
    home_away: list[dict],
    fixtures_by_team: dict[str, list[dict]],
    current_gw: int,
    season_label: str,
    generated_at: str,
) -> str:
    html = TEMPLATE_PATH.read_text()

    substitutions = [
        ("DATA", _DATA_RE, f"const DATA = {json.dumps(league_table)};"),
        ("HOME_AWAY", _HOME_AWAY_RE, f"const HOME_AWAY = {json.dumps(home_away)};"),
        ("FIXTURES_BY_TEAM", _FIXTURES_RE, f"const FIXTURES_BY_TEAM = {json.dumps(fixtures_by_team)};"),
        (
            "eyebrow",
            _EYEBROW_RE,
            f'<span class="eyebrow">Premier League &middot; {season_label} &middot; '
            f'after Gameweek {current_gw}</span>',
        ),
        (
            "asof",
            _ASOF_RE,
            f'document.getElementById("asof").textContent = "Refreshed {generated_at}";',
        ),
    ]

    for name, pattern, replacement in substitutions:
        html, count = pattern.subn(lambda _m, r=replacement: r, html, count=1)
        if count != 1:
            raise RuntimeError(f"template substitution for {name} did not match exactly once")

    return html
