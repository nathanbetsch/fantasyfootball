"""NFL bye weeks, from ESPN's public (no-login) schedule endpoint."""
from __future__ import annotations

import requests

from .cache import cached

URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}?view=proTeamSchedules_wl"

# ESPN abbreviations that differ from Sleeper's
ESPN_TO_STD = {"WSH": "WAS"}


def std_team(abbrev: str | None) -> str:
    a = (abbrev or "FA").upper()
    return ESPN_TO_STD.get(a, a)


@cached(ttl=12 * 3600)
def bye_weeks(season: int) -> dict[str, int]:
    """{team abbrev: bye week}"""
    try:
        data = requests.get(URL.format(season=season), timeout=15).json()
    except Exception:
        return {}
    return {
        std_team(t["abbrev"]): t.get("byeWeek")
        for t in data.get("settings", {}).get("proTeams", [])
        if t.get("byeWeek")
    }


@cached(ttl=12 * 3600)
def espn_team_ids(season: int) -> dict[int, str]:
    """{ESPN proTeamId: team abbrev}"""
    try:
        data = requests.get(URL.format(season=season), timeout=15).json()
    except Exception:
        return {}
    return {t["id"]: std_team(t["abbrev"]) for t in data.get("settings", {}).get("proTeams", [])}
