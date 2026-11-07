"""Free NFL data feeds polled every run: injury report, news, Sleeper trending adds."""
from __future__ import annotations

from dataclasses import dataclass

import requests

from .byes import std_team
from .models import player_key

ESPN_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
ESPN_NEWS = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news?limit=50"
SLEEPER_TRENDING = "https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours={hours}&limit={limit}"

SKILL = {"QB", "RB", "WR", "TE"}
# ESPN injury statuses, worst last
SEVERITY = {"Active": 0, "Questionable": 1, "Doubtful": 2, "Out": 3, "Injured Reserve": 4}
SHORT = {"Injured Reserve": "IR"}


@dataclass
class Injury:
    key: str
    name: str
    position: str
    team: str
    status: str  # one of SEVERITY
    comment: str

    @property
    def severity(self) -> int:
        return SEVERITY.get(self.status, 0)

    @property
    def short(self) -> str:
        return SHORT.get(self.status, self.status)


@dataclass
class Article:
    id: str
    headline: str
    url: str
    published: str
    athletes: list[str]  # player names tagged on the story


@dataclass
class Trending:
    sleeper_id: str
    count: int


def injuries() -> dict[str, Injury]:
    """{player_key: Injury} for fantasy skill positions on ESPN's injury report."""
    data = requests.get(ESPN_INJURIES, timeout=20).json()
    out: dict[str, Injury] = {}
    for team in data.get("injuries", []):
        for i in team.get("injuries", []):
            a = i.get("athlete", {})
            pos = (a.get("position") or {}).get("abbreviation", "")
            if pos not in SKILL or i.get("status") not in SEVERITY:
                continue
            key = player_key(a.get("displayName", ""), pos)
            out[key] = Injury(
                key=key,
                name=a.get("displayName", ""),
                position=pos,
                team=std_team((a.get("team") or {}).get("abbreviation")),
                status=i["status"],
                comment=i.get("shortComment", ""),
            )
    return out


def news() -> list[Article]:
    data = requests.get(ESPN_NEWS, timeout=20).json()
    out = []
    for a in data.get("articles", []):
        out.append(Article(
            id=str(a.get("id")),
            headline=a.get("headline", ""),
            url=(a.get("links", {}).get("web") or {}).get("href", ""),
            published=a.get("published", ""),
            athletes=[c.get("description", "") for c in a.get("categories", []) if c.get("type") == "athlete"],
        ))
    return out


def trending(hours: int = 12, limit: int = 25) -> list[Trending]:
    data = requests.get(SLEEPER_TRENDING.format(hours=hours, limit=limit), timeout=20).json()
    return [Trending(t["player_id"], t.get("count", 0)) for t in data]
