"""Pull every league together and compute lineup warnings + cross-league exposure."""
from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass

from . import espn, sleeper
from .byes import bye_weeks
from .cache import cached
from .models import League, Player, Warning

DANGER_INJURIES = {"Out", "IR", "Doubtful", "Sus", "PUP", "NA"}


@dataclass
class Exposure:
    name: str
    position: str
    team: str
    injury: str
    leagues: list[str]


@dataclass
class Dashboard:
    leagues: list[League]
    exposure: list[Exposure]
    week: int
    total_warnings: int


def _warn(league: League) -> None:
    for slot in league.empty_slots:
        league.warnings.append(Warning("danger", f"Empty starting slot: {slot}"))
    for p in league.starters:
        if p.bye_week and p.bye_week == league.week:
            league.warnings.append(Warning("danger", f"{p.name} ({p.team}) is on BYE but starting at {p.slot}"))
        elif p.injury in DANGER_INJURIES:
            league.warnings.append(Warning("danger", f"{p.name} is {p.injury} but starting at {p.slot}"))
        elif p.injury == "Questionable":
            league.warnings.append(Warning("caution", f"{p.name} is Questionable (starting at {p.slot})"))
    # An Out/IR player sitting on the bench while the IR slot is empty wastes a roster spot.
    if not any(p.slot == "IR" for p in league.players):
        hurt_bench = [p for p in league.bench if p.slot == "BN" and p.injury in ("IR", "Out")]
        for p in hurt_bench[:2]:
            league.warnings.append(Warning("caution", f"{p.name} ({p.injury}) is on your bench; move him to IR if your league allows it"))


@cached(ttl=120)
def build_dashboard() -> Dashboard:
    season = int(os.getenv("SEASON", "2026"))
    byes = bye_weeks(season)
    leagues: list[League] = []

    username = os.getenv("SLEEPER_USERNAME", "").strip()
    if username:
        try:
            leagues += sleeper.fetch_leagues(username, season, byes)
        except Exception as e:
            leagues.append(League("Sleeper", f"Sleeper ({username})", "", 0, error=str(e)))

    espn_id = os.getenv("ESPN_LEAGUE_ID", "").strip()
    if espn_id:
        try:
            leagues.append(espn.fetch_league(
                espn_id, season,
                os.getenv("ESPN_S2", "").strip(), os.getenv("ESPN_SWID", "").strip(),
                os.getenv("ESPN_LEAGUE_TYPE", "redraft"), byes,
            ))
        except Exception as e:
            leagues.append(League("ESPN", f"ESPN league {espn_id}", "", 0, error=str(e)))

    for lg in leagues:
        if not lg.error:
            _warn(lg)

    # Tab order: LEAGUE_ORDER="We Cummin, LikingGirlsLovinBoys, ..." (unlisted leagues go last)
    order = [n.strip().lower() for n in os.getenv("LEAGUE_ORDER", "").split(",") if n.strip()]
    rank = lambda lg: order.index(lg.name.lower()) if lg.name.lower() in order else len(order)
    leagues.sort(key=rank)  # stable: keeps fetch order for unlisted leagues

    owned: dict[str, list[tuple[Player, str]]] = defaultdict(list)
    for lg in leagues:
        for p in lg.players:
            owned[p.key].append((p, lg.name))
    exposure = sorted(
        (Exposure(ps[0][0].name, ps[0][0].position, ps[0][0].team, ps[0][0].injury, [n for _, n in ps])
         for ps in owned.values() if len(ps) > 1),
        key=lambda x: (-len(x.leagues), x.name),
    )

    week = max((lg.week for lg in leagues), default=0)
    return Dashboard(leagues, exposure, week, sum(len(lg.warnings) for lg in leagues if not lg.error))
