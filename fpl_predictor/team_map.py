"""Understat team title -> FPL short_name.

Hand-maintained, not fetched: the two sources spell team names differently
("Coventry" vs "Coventry City", "Manchester United" vs "Man Utd") and the
20-team set only changes once a season (promotion/relegation), so a static
table is simpler and more robust than fuzzy-matching names every run.
"""

UNDERSTAT_TO_FPL = {
    "Chelsea": "CHE",
    "Arsenal": "ARS",
    "Manchester City": "MCI",
    "Hull": "HUL",
    "Everton": "EVE",
    "Newcastle United": "NEW",
    "Brentford": "BRE",
    "Leeds": "LEE",
    "Sunderland": "SUN",
    "Manchester United": "MUN",
    "Brighton": "BHA",
    "Ipswich": "IPS",
    "Liverpool": "LIV",
    "Bournemouth": "BOU",
    "Nottingham Forest": "NFO",
    "Aston Villa": "AVL",
    "Crystal Palace": "CRY",
    "Tottenham": "TOT",
    "Fulham": "FUL",
    "Coventry": "COV",
}
