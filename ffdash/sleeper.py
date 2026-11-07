"""Sleeper public API client (read-only, no login needed). Docs: https://docs.sleeper.com"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from .cache import cached
from .models import League, Matchup, Player

API = "https://api.sleeper.app/v1"
PLAYERS_FILE = Path(__file__).resolve().parent.parent / "cache" / "sleeper_players.json"
LEAGUE_TYPES = {0: "redraft", 1: "keeper", 2: "dynasty"}
SLOT_NAMES = {"SUPER_FLEX": "SFLEX", "REC_FLEX": "W/T", "WRRB_FLEX": "W/R"}


def _get(path: str):
    r = requests.get(f"{API}{path}", timeout=20)
    r.raise_for_status()
    return r.json()


@cached(ttl=300)
def nfl_state() -> dict:
    return _get("/state/nfl")


@cached(ttl=3600)
def players_db() -> dict[str, dict]:
    """All NFL players (~5 MB from Sleeper). Trimmed and cached on disk for a day,
    as Sleeper asks callers to fetch this at most once per day."""
    if PLAYERS_FILE.exists() and time.time() - PLAYERS_FILE.stat().st_mtime < 86400:
        return json.loads(PLAYERS_FILE.read_text(encoding="utf-8"))
    raw = _get("/players/nfl")
    slim = {
        pid: {
            "name": p.get("full_name")
            or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "pos": p.get("position") or "",
            "team": p.get("team") or "FA",
            "injury": p.get("injury_status") or "",
        }
        for pid, p in raw.items()
    }
    PLAYERS_FILE.parent.mkdir(exist_ok=True)
    PLAYERS_FILE.write_text(json.dumps(slim), encoding="utf-8")
    return slim


def _player(pid: str, slot: str, db: dict, byes: dict, points: dict) -> Player:
    p = db.get(pid)
    if p is None:  # team defenses use the team abbrev as their id
        p = {"name": f"{pid} D/ST", "pos": "DEF", "team": pid, "injury": ""}
    return Player(
        name=p["name"],
        position=p["pos"],
        team=p["team"],
        slot=slot,
        injury=p["injury"],
        bye_week=byes.get(p["team"]),
        points=points.get(pid),
    )


def fetch_leagues(username: str, season: int, byes: dict[str, int]) -> list[League]:
    user = _get(f"/user/{username}")
    if not user:
        raise ValueError(f"Sleeper user '{username}' not found")
    uid = user["user_id"]
    state = nfl_state()
    week = int(state.get("display_week") or state.get("week") or 1)
    db = players_db()

    leagues = []
    for lg in _get(f"/user/{uid}/leagues/nfl/{season}") or []:
        league = League(
            platform="Sleeper",
            name=lg["name"],
            league_type=LEAGUE_TYPES.get(lg.get("settings", {}).get("type", 0), "redraft"),
            week=week,
            num_teams=lg.get("total_rosters", 0),
            url=f"https://sleeper.com/leagues/{lg['league_id']}",
        )
        try:
            _fill_league(league, lg, uid, db, byes)
        except Exception as e:  # one broken league shouldn't sink the page
            league.error = f"Couldn't load this league: {e}"
        leagues.append(league)
    return leagues


def _fill_league(league: League, lg: dict, uid: str, db: dict, byes: dict) -> None:
    lid = lg["league_id"]
    rosters = _get(f"/league/{lid}/rosters")
    users = {u["user_id"]: u for u in _get(f"/league/{lid}/users")}
    matchups = _get(f"/league/{lid}/matchups/{league.week}") or []

    def team_name(roster) -> str:
        u = users.get(roster.get("owner_id"), {})
        return (u.get("metadata") or {}).get("team_name") or u.get("display_name") or "Unknown"

    mine = next(
        (r for r in rosters if r.get("owner_id") == uid or uid in (r.get("co_owners") or [])),
        None,
    )
    if mine is None:
        raise ValueError("no roster owned by you in this league")

    s = mine.get("settings", {})
    league.team_name = team_name(mine)
    league.wins, league.losses, league.ties = s.get("wins", 0), s.get("losses", 0), s.get("ties", 0)
    league.points_for = s.get("fpts", 0) + s.get("fpts_decimal", 0) / 100

    def sort_key(r):
        rs = r.get("settings", {})
        return (-rs.get("wins", 0), -(rs.get("fpts", 0) + rs.get("fpts_decimal", 0) / 100))

    league.standing = sorted(rosters, key=sort_key).index(mine) + 1

    # This week's matchup
    by_roster = {m["roster_id"]: m for m in matchups}
    my_m = by_roster.get(mine["roster_id"])
    points = (my_m or {}).get("players_points") or {}
    if my_m and my_m.get("matchup_id") is not None:
        opp_m = next(
            (m for m in matchups if m["matchup_id"] == my_m["matchup_id"] and m["roster_id"] != mine["roster_id"]),
            None,
        )
        if opp_m:
            opp_roster = next(r for r in rosters if r["roster_id"] == opp_m["roster_id"])
            league.matchup = Matchup(my_m.get("points") or 0, team_name(opp_roster), opp_m.get("points") or 0)

    # Lineup: starters line up with the non-bench roster_positions. The weekly matchup
    # holds the real current lineup; the roster's own "starters" can be stale.
    slots = [p for p in lg.get("roster_positions", []) if p != "BN"]
    starters = (my_m or {}).get("starters") or mine.get("starters") or []
    for slot, pid in zip(slots, starters):
        slot = SLOT_NAMES.get(slot, slot)
        if not pid or pid == "0":
            league.empty_slots.append(slot)
        else:
            league.players.append(_player(pid, slot, db, byes, points))

    reserve = set(mine.get("reserve") or [])
    taxi = set(mine.get("taxi") or [])
    for pid in mine.get("players") or []:
        if pid in starters:
            continue
        slot = "IR" if pid in reserve else "TAXI" if pid in taxi else "BN"
        league.players.append(_player(pid, slot, db, byes, points))
