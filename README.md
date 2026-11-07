# FPL xG Predictor

A Premier League dashboard for Fantasy Premier League decisions, built on
expected goals (xG) instead of raw goals and points.

**Live:** https://fpl-predictor-nine.vercel.app

It shows:

- **xG League Table** — each team's attack (xG) and defence (xGC, expected
  goals conceded) this season, alongside actual goals and points
- **Home / Away Split** — the same xG numbers split by venue, since many
  teams play very differently at home and away
- **Attacking Fixture Ticker** — for picking attackers: each upcoming
  fixture is coloured by how leaky the opponent's defence is at that venue
- **Defensive Fixture Ticker** — for picking defenders and keepers: each
  fixture is coloured by how weak the opponent's attack is at that venue

Teams, fixtures and results come from the official
[FPL API](https://fantasy.premierleague.com). xG comes from one of two
sources, switched with `XG_SOURCE` (see `fpl_predictor/config.py`):

- `fpl` (default) — the FPL API itself: a team's xG in a match is the sum
  of its players' Opta xG, and its xGC is the opponent's xG
- `understat` — [Understat](https://understat.com)'s team-level match xG

To flip the live site, set a repository variable `XG_SOURCE` (Settings →
Secrets and variables → Actions → Variables) to `fpl` or `understat`, then
re-run the deploy workflow. Locally: `XG_SOURCE=understat python -m
fpl_predictor refresh`.

## Running locally

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m fpl_predictor refresh   # fetch live data and build
```

This writes `output/dashboard.html`; open it in a browser.
`python -m fpl_predictor build` rebuilds from the cached data in
`data/cache/` without hitting the network.

## Deployment

Every push to `master` runs `.github/workflows/deploy.yml`, which fetches
fresh data, builds the dashboard and deploys it to Vercel.

The same workflow also runs every 3 hours and redeploys once a new
gameweek has finished on FPL and its results are confirmed (and, when
using Understat, Understat has them too; `python -m fpl_predictor check`
decides). If that ever fails, the page
notices on its own: 36 hours after the next gameweek's last kickoff it
shows a "data may be out of date" modal.
