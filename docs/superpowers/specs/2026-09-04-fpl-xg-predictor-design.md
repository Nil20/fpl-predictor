# FPL xG-based Fixture & Form Predictor — Design

Date: 2026-09-04
Status: Approved for planning

## Purpose

Help decide FPL transfers/captaincy by looking at real underlying-quality
stats (xG, xA, xGC) rather than raw goals/points, split by home vs away,
since teams often perform very differently at home vs away. Answers three
questions:

1. How strong is each team's attack and defense, at home and away, based on
   recent matches?
2. Which teams have the most favorable run of fixtures over the next N
   gameweeks, and how "easy" is each specific fixture (color-coded tiers)?
3. Which players have rising/falling underlying xG/xA involvement?

## Non-goals (for this version)

- No web dashboard — CLI + generated charts/tables only.
- No authentication / private-team features (own live picks, transfers).
- No Poisson probability modeling — rolling averages only, for now.
- No database — flat files (cached JSON + derived CSV) are enough.
- No multi-season history — current season only (FPL's own API doesn't
  expose match-by-match history for past seasons anyway, only season
  totals).

## Data source

Official FPL API only, unauthenticated:

- `GET /api/bootstrap-static/` — players, teams, gameweek calendar.
- `GET /api/fixtures/` — full fixture list, past results and upcoming
  schedule.
- `GET /api/element-summary/{player_id}/` — per-player match-by-match
  history for the current season: `expected_goals`, `expected_assists`,
  `expected_goal_involvements`, `expected_goals_conceded`, `was_home`,
  `opponent_team`, `round`, per fixture.

Team-level xG/xGC is not exposed directly and is derived:

- **Team xG for a match** = sum of `expected_goals` across all of that
  team's players who appear in that fixture's rows.
- **Team xGC for a match** = `expected_goals_conceded` from any one of that
  team's players in that fixture (the API replicates the same team-level
  value on every player row for that match).

This requires pulling `element-summary` for every player who has featured
this season (roughly 500-600 calls), done once and cached.

## Components

### 1. `fpl_client` (data layer)

- Thin wrapper functions for the three endpoints above.
- Bulk-fetches all players' `element-summary` concurrently (httpx +
  asyncio) rather than serially.
- Caches raw JSON responses to disk (e.g. `data/cache/`), keyed by
  endpoint + id. A `--refresh` CLI flag forces re-fetching (used after new
  gameweeks complete); otherwise cached data is reused.

### 2. `build_team_match_stats` (aggregation)

- Consumes the cached raw JSON and produces one tidy table: one row per
  (team, fixture) with columns `team, gw, opponent, was_home, xG, xGC`.
- Saved to `data/team_matches.csv` for reuse by the analysis layer.
- Pure transformation logic (no network calls) — unit-testable against
  fixture JSON samples.

### 3. `analysis` (rolling averages)

- Given the team-match table, computes rolling averages **separately for
  home rows and away rows** per team, over a configurable window (default:
  last 6 home / last 6 away matches):
  - Attack strength = rolling avg xG (home, away).
  - Defense strength = rolling avg xGC (home, away).
- Window size is a parameter, not hardcoded.
- Also computes the same rolling-average logic over each player's
  `expected_goal_involvements` (xG + xA) for the player-trends view, reusing
  the already-cached element-summary data (no extra fetching).

### 4. `fixture_ticker` (banding + output)

- For each upcoming fixture, looks up the **venue-specific** xGC of the
  team being played against (their home xGC if they're at home, away xGC if
  away) from the analysis layer's rolling averages.
- Ranks all 20 teams by that venue-specific xGC, descending, and splits
  them into **K equal-count bands** (K is a CLI flag, default 5). If 20
  isn't evenly divisible by K, leftover teams are distributed one-per-band
  starting from the top (easiest) band.
- Maps bands to a green→dark color scale (highest xGC/easiest = green,
  lowest xGC/hardest = dark) using a matplotlib colormap, so it isn't
  hardcoded to exactly 5 colors.
- For a chosen window of **N gameweeks ahead** (CLI flag), renders a
  per-gameweek ticker: rows = teams, columns = next N gameweeks, each cell
  = opponent + venue, colored by that opponent's band for that fixture.
- Bands are recomputed fresh each run from current rolling-average data,
  not cached/frozen — they'll shift as more gameweeks are played.

### 5. CLI entrypoint

- A small `main.py` (argparse-based) exposing subcommands, e.g.:
  - `refresh` — re-pull data from the API.
  - `strength [--window N]` — table of home/away attack/defense per team.
  - `ticker [--gameweeks N] [--bands K]` — the color-coded fixture ticker.
  - `players [--window N]` — player xG/xA involvement trend table/chart.
- Charts rendered via matplotlib, saved to `data/output/` (or shown
  interactively) rather than embedded in a web UI.

## Data flow

```
FPL API ──(fpl_client, cached)──> raw JSON
                                     │
                          build_team_match_stats
                                     │
                                     ▼
                        data/team_matches.csv
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                  ▼
                analysis                        analysis (player trends)
         (home/away rolling avgs)             (xG+xA rolling avg per player)
                    │                                  │
                    ▼                                  ▼
             fixture_ticker                      players table/chart
          (banding + color ticker)
                    │
                    ▼
              CLI output (tables / matplotlib charts)
```

## Testing

- `build_team_match_stats` and `analysis` are pure functions over
  dataframes — unit tests using small hand-built fixture/player JSON
  samples, covering: correct home/away split, correct xGC dedup per team
  per match, rolling window edge cases (fewer matches than window size).
- `fixture_ticker` banding logic — unit tests covering equal-count binning
  with K dividing 20 evenly and not evenly (leftover distribution).
- `fpl_client` — no unit tests against the live API; a manual smoke check
  (`refresh` command) is enough for this version.

## Tech stack

Python, pandas for data wrangling, httpx + asyncio for concurrent fetches,
matplotlib for charts, argparse for the CLI. No database, no web framework.
