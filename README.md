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

Data comes from [Understat](https://understat.com) (xG) and the official
[FPL API](https://fantasy.premierleague.com) (teams and fixtures).

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
