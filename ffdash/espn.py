"""ESPN fantasy API client (unofficial). Private leagues need the espn_s2 + SWID
cookies from a logged-in browser session."""
from __future__ import annotations

from collections import Counter

import requests

from .byes import espn_team_ids
from .models import League, Matchup, Player, player_key

API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}"

POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}
SLOTS = {
    0: "QB", 2: "RB", 3: "W/R", 4: "WR", 5: "W/T", 6: "TE", 7: "SFLEX",
    16: "DEF", 17: "K", 20: "BN", 21: "IR", 23: "FLEX",
}
INJURY = {
    "QUESTIONABLE": "Questionable", "DOUBTFUL": "Doubtful", "OUT": "Out",
    "INJURY_RESERVE": "IR", "SUSPENSION": "Sus", "DAY_TO_DAY": "Questionable",
}


class EspnAuthError(Exception):
    pass


def fetch_league(league_id: str, season: int, espn_s2: str, swid: str, league_type: str,
                 byes: dict[str, int]) -> League:
    swid = swid.strip()
    if swid and not swid.startswith("{"):
        swid = "{" + swid.strip("{}") + "}"
    r = requests.get(
        API.format(season=season, league_id=league_id),
        params=[("view", v) for v in ("mTeam", "mRoster", "mMatchupScore", "mSettings", "mStandings")],
        cookies={"espn_s2": espn_s2, "SWID": swid} if espn_s2 else None,
        timeout=20,
    )
    if r.status_code in (401, 403):
        raise EspnAuthError(
            "ESPN said this league is private. Add ESPN_S2 and ESPN_SWID to your .env file "
            "(see README), then restart."
            if not espn_s2 else
            "ESPN rejected the login cookies. They may have expired; copy fresh ESPN_S2 and "
            "ESPN_SWID values into .env and restart."
        )
    r.raise_for_status()
    data = r.json()

    week = data.get("scoringPeriodId") or data.get("status", {}).get("currentMatchupPeriod", 1)
    period = data.get("status", {}).get("currentMatchupPeriod", week)
    teams = data.get("teams", [])
    pro_teams = espn_team_ids(season)

    def team_name(t) -> str:
        return t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip() or f"Team {t['id']}"

    mine = next((t for t in teams if swid and swid in (t.get("owners") or [])), None)
    league = League(
        platform="ESPN",
        name=data.get("settings", {}).get("name", f"ESPN {league_id}"),
        league_type=league_type,
        week=week,
        num_teams=len(teams),
        url=f"https://fantasy.espn.com/football/team?leagueId={league_id}"
            + (f"&teamId={mine['id']}" if mine else ""),
    )
    if mine is None:
        league.error = "Couldn't find your team. Check that ESPN_SWID belongs to the account that owns a team here."
        return league

    rec = mine.get("record", {}).get("overall", {})
    league.team_name = team_name(mine)
    league.wins, league.losses, league.ties = rec.get("wins", 0), rec.get("losses", 0), rec.get("ties", 0)
    league.points_for = rec.get("pointsFor", 0.0)
    league.standing = mine.get("playoffSeed") or mine.get("rankCalculatedFinal") or None

    # Matchup this period
    for m in data.get("schedule", []):
        if m.get("matchupPeriodId") != period:
            continue
        home, away = m.get("home", {}), m.get("away", {})
        if mine["id"] not in (home.get("teamId"), away.get("teamId")):
            continue
        me, opp = (home, away) if home.get("teamId") == mine["id"] else (away, home)
        opp_team = next((t for t in teams if t["id"] == opp.get("teamId")), None)
        pts = lambda side: side.get("totalPointsLive", side.get("totalPoints", 0)) or 0
        league.matchup = Matchup(pts(me), team_name(opp_team) if opp_team else "BYE", pts(opp))
        break

    # Roster
    filled = Counter()
    for e in mine.get("roster", {}).get("entries", []):
        slot_id = e.get("lineupSlotId")
        slot = SLOTS.get(slot_id, str(slot_id))
        pl = e.get("playerPoolEntry", {}).get("player", {})
        team = pro_teams.get(pl.get("proTeamId"), "FA")
        stats = [s for s in pl.get("stats", []) if s.get("scoringPeriodId") == week and s.get("statSourceId") == 0]
        league.players.append(Player(
            name=pl.get("fullName", "Unknown"),
            position=POSITIONS.get(pl.get("defaultPositionId"), "?"),
            team=team,
            slot=slot,
            injury=INJURY.get(pl.get("injuryStatus") or "", ""),
            bye_week=byes.get(team),
            # No actual stats for this week yet = hasn't played. (appliedStatTotal is
            # the most recent week with stats, which is often last week, so don't use it.)
            points=stats[0].get("appliedTotal", 0.0) if stats else 0.0,
        ))
        filled[slot_id] += 1

    # Who is rostered anywhere in the league (everyone else is on waivers / FA)
    for t in teams:
        for e in t.get("roster", {}).get("entries", []):
            pl = e.get("playerPoolEntry", {}).get("player", {})
            pos = POSITIONS.get(pl.get("defaultPositionId"))
            if pos:
                league.rostered.add(player_key(pl.get("fullName", ""), pos))

    # Starting slots + empty ones
    counts = data.get("settings", {}).get("rosterSettings", {}).get("lineupSlotCounts", {})
    for sid_str, n in sorted(counts.items(), key=lambda kv: int(kv[0])):
        sid = int(sid_str)
        if sid in (20, 21) or sid not in SLOTS or not n:
            continue
        league.starting_slots += [SLOTS[sid]] * n
        for _ in range(max(0, n - filled[sid])):
            league.empty_slots.append(SLOTS[sid])
    return league
