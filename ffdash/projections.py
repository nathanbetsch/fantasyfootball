"""Sleeper weekly projections -> this week's and rest-of-season points per player.

Each week's file is ~2 MB, so they're slimmed and cached on disk for 12 hours.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from .models import League, player_key

URL = ("https://api.sleeper.app/projections/nfl/{season}/{week}?season_type=regular"
       "&position%5B%5D=QB&position%5B%5D=RB&position%5B%5D=WR&position%5B%5D=TE"
       "&position%5B%5D=K&position%5B%5D=DEF")
CACHE = Path(__file__).resolve().parent.parent / "cache" / "proj"
LAST_WEEK = 17  # fantasy seasons end in week 17
FIELD = {"ppr": 0, "half": 1, "std": 2}


def week_proj(season: int, week: int) -> dict[str, list[float]]:
    """{sleeper_id: [ppr, half, std]}"""
    path = CACHE / f"{season}-w{week}.json"
    if path.exists() and time.time() - path.stat().st_mtime < 12 * 3600:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        data = requests.get(URL.format(season=season, week=week), timeout=30).json()
    except Exception:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    slim = {}
    for row in data:
        s = row.get("stats") or {}
        if s.get("pts_ppr") is not None:
            slim[row["player_id"]] = [s.get("pts_ppr") or 0, s.get("pts_half_ppr") or 0, s.get("pts_std") or 0]
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(slim), encoding="utf-8")
    return slim


class Projections:
    def __init__(self, season: int, week: int, db: dict[str, dict]):
        self.week = week
        self.db = db
        self.this_week = week_proj(season, week)
        self.weeks_left = max(1, LAST_WEEK - week + 1)
        self.ros: dict[str, list[float]] = {}
        for w in range(week, LAST_WEEK + 1):
            for pid, pts in week_proj(season, w).items():
                tot = self.ros.setdefault(pid, [0.0, 0.0, 0.0])
                for i in range(3):
                    tot[i] += pts[i]
        # ESPN players have no Sleeper id: match by name + position
        self.by_key = {player_key(p["name"], p["pos"]): pid for pid, p in db.items() if p.get("pos")}

    def pid_for(self, name: str, pos: str) -> str:
        return self.by_key.get(player_key(name, pos), "")

    def enrich(self, league: League) -> None:
        f = FIELD.get(league.scoring, 0)
        seen = set()
        for team in league.teams:
            for p in team.players:
                if id(p) in seen:
                    continue
                seen.add(id(p))
                if not p.pid:
                    p.pid = self.pid_for(p.name, p.position)
                if p.age is None:
                    p.age = self.db.get(p.pid, {}).get("age")
                wk = self.this_week.get(p.pid)
                p.proj = round(wk[f], 1) if wk and p.bye_week != league.week else 0.0
                ros = self.ros.get(p.pid)
                p.ros = round(ros[f], 1) if ros else 0.0
