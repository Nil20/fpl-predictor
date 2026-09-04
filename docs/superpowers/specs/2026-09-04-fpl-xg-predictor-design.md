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

Two sources, each used for what it's authoritative for — confirmed by
pulling real data from both during design (see Appendix):

- **Understat** — primary source for team and player xG/xA/xGC.
  `GET https://understat.com/getLeagueData/EPL/{season}` (gzip-compressed
  JSON; needs a browser-like `User-Agent`) returns, in one call:
  - `teams[id].history` — one row per match already at **team level**:
    `h_a` (home/away), `xG`, `xGA` (= our xGC), `scored`, `missed`, `pts`,
    `result`, `date`. No per-player aggregation needed, no dedup risk.
  - `players` — season-to-date `xG`/`xA` per player, with team and
    position.
  - `dates` — full 380-fixture list with actual goals, both teams' match
    xG, and Understat's own win/draw/loss forecast probabilities.
- **FPL API** — primary source for the gameweek/fixture calendar and
  prices, unauthenticated:
  - `GET /api/bootstrap-static/` — players (prices, ownership %), teams,
    gameweek calendar (deadlines, current/next/finished flags).
  - `GET /api/fixtures/` — full fixture list, each tagged with an `event`
    (gameweek) number. This is the only source that correctly reflects
    **blank gameweeks** (a team has no fixture that GW) and **double
    gameweeks** (a team has two fixtures in one GW) — Understat's `dates`
    are just chronological with no gameweek number, so FPL's `fixtures` is
    the one authoritative source for "which gameweek is this match in."

Because Understat gives team-level match rows without gameweek numbers,
and FPL gives gameweek numbers without match-level xG, the two must be
**joined**: each Understat team-match row is matched to its FPL fixture by
(team, opponent, date), so it inherits the correct `gw`. This also means
team names must be reconciled — Understat's team titles don't match FPL's
(`"Coventry"` vs `"Coventry City"`, `"Manchester United"` vs `"Man Utd"`,
`"Nott'm Forest"` vs Understat's own spelling, etc.) — via a small static
~20-row mapping table.

This is a meaningfully simpler pipeline than deriving team xG/xGC from FPL
alone: instead of ~500-600 `element-summary` calls plus fragile per-match
dedup logic (which broke during design — see Appendix), it's 2 FPL calls
plus 1 Understat call, joined on (team, opponent, date).

## Components

### 1. `understat_client` / `fpl_client` (data layer)

- `understat_client`: one function to fetch and gzip-decode
  `getLeagueData/EPL/{season}`, cached to disk raw.
- `fpl_client`: thin wrappers for `bootstrap-static` and `fixtures`,
  cached to disk raw.
- A `--refresh` CLI flag forces re-fetching both sources (used after new
  gameweeks complete); otherwise cached data is reused. No concurrency
  needed — it's 3 HTTP calls total, not hundreds.

### 2. `team_name_map`

- Static mapping table (~20 rows) from Understat team titles to FPL team
  ids/short names. Small, hand-maintained, checked into the repo (not
  fetched) — team names don't change mid-season.

### 3. `build_team_match_stats` (join)

- Joins each Understat team-match row (`teams[id].history`) to its FPL
  fixture by (team via name map, opponent, date), producing one tidy
  table: one row per (team, fixture) with columns
  `team, gw, opponent, was_home, xG, xGC` — `xG`/`xGC` straight from
  Understat, `gw`/`was_home` cross-checked against FPL's fixture record.
- Saved to `data/team_matches.csv` for reuse by the analysis layer.
- Pure transformation logic (no network calls) — unit-testable against
  small hand-built Understat/FPL JSON samples, including a blank-gameweek
  case (team missing from an FPL event) and a double-gameweek case (team
  has two fixtures, hence two rows, in one FPL event).

### 4. `analysis` (rolling averages)

- Given the team-match table, computes rolling averages **separately for
  home rows and away rows** per team, over a configurable window (default:
  last 6 home / last 6 away matches):
  - Attack strength = rolling avg xG (home, away).
  - Defense strength = rolling avg xGC (home, away).
- Window size is a parameter, not hardcoded.
- Also computes the same rolling-average logic over each player's
  `xG + xA` (season-to-date, from Understat's `players` list) for the
  player-trends view. Understat's per-league response only carries
  season-totals per player, not a match-by-match log, so a rolling
  *window* over individual matches isn't available from this endpoint —
  if per-match player trend granularity turns out to matter once we're
  looking at real output, the fallback is FPL's own
  `element-summary/{id}` history (safe to use per-player, since the
  aggregation bug we hit was specifically about summing/deduping *across*
  players for a team, not about reading one player's own match log).

### 5. `fixture_ticker` (banding + output)

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

### 6. CLI entrypoint

- A small `main.py` (argparse-based) exposing subcommands, e.g.:
  - `refresh` — re-pull data from the API.
  - `strength [--window N]` — table of home/away attack/defense per team.
  - `ticker [--gameweeks N] [--bands K]` — the color-coded fixture ticker.
  - `players [--window N]` — player xG/xA involvement trend table/chart.
- Charts rendered via matplotlib, saved to `data/output/` (or shown
  interactively) rather than embedded in a web UI.

## Data flow

```
Understat ──(understat_client, cached)──> raw JSON ─┐
                                                      ├── build_team_match_stats
FPL API ──(fpl_client, cached)──> raw JSON ──────────┘    (join via team_name_map)
                                                      │
                                                      ▼
                                          data/team_matches.csv
                                                      │
                    ┌─────────────────────────────────┴────────────────┐
                    ▼                                                   ▼
                analysis                                    analysis (player trends)
         (home/away rolling avgs)                    (season-to-date xG+xA per player)
                    │                                                   │
                    ▼                                                   ▼
             fixture_ticker                                     players table/chart
    (banding + color ticker, blank/double-GW aware)
                    │
                    ▼
              CLI output (tables / matplotlib charts)
```

## Testing

- `build_team_match_stats` — pure join logic over small hand-built
  Understat/FPL JSON samples: correct home/away split, correct team-name
  mapping, correct gameweek join including a blank-gameweek case and a
  double-gameweek case (two rows for one team in one FPL event).
- `analysis` — pure functions over the resulting table: rolling window
  edge cases (fewer matches than window size), home/away kept separate.
- `fixture_ticker` banding logic — unit tests covering equal-count binning
  with K dividing 20 evenly and not evenly (leftover distribution), plus
  rendering a blank-gameweek cell and a double-gameweek cell correctly.
- `understat_client` / `fpl_client` — no unit tests against the live
  APIs; a manual smoke check (`refresh` command) is enough for this
  version.

## Tech stack

Python, pandas for data wrangling, `requests` for the (now just 3, no
concurrency needed) HTTP calls, matplotlib for charts, argparse for the
CLI. No database, no web framework.

## Appendix: data verified during design

Pulled live during design (2026-09-04/05, gameweeks 1-2 finished, GW3
upcoming) to settle the FPL-vs-Understat question:

- FPL's `bootstrap-static` `teams[].played`/`points`/`win`/`draw`/`loss`
  are **not populated** by the live API — goals/points/results have to be
  computed from `fixtures` results directly, not read off `teams`.
- Deriving team xG/xGC from FPL alone requires summing/deduping across
  ~360 players' `element-summary` histories. This broke in two ways
  during a real attempt: (1) crediting match rows to a player's *current*
  team misattributes matches for anyone who changed clubs mid-window
  (fixed by deriving the team from the fixture's home/away side instead
  of the player's current team); (2) even after that fix, the assumption
  that `expected_goals_conceded` replicates identically across all of a
  team's players in a match did not hold cleanly for at least one team
  (Chelsea) in spot-checking — the two goalkeeper apps in the same match
  needed a value the aggregation didn't cleanly resolve. This class of
  bug is why Understat (already team-level, no replication assumption)
  was adopted instead.
- Understat's `getLeagueData/EPL/2026` team-match history independently
  reproduced FPL's actual goals for/against exactly (cross-checked
  against Aston Villa: 0 scored / 5 conceded both ways), confirming it's
  a reliable substitute.
- Understat's team/competition names for the 2026/2027 season use
  promoted sides Leeds, Sunderland, and — per this live pull — also
  Hull City, Coventry City and Ipswich Town appear in this season's FPL
  data; a real-connectivity check (TLS cert, resolved IPs) confirmed this
  is genuinely live 2026/2027 data and not a stale/mock response, just a
  season past this project's knowledge cutoff.
