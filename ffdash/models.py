"""Platform-neutral data shapes so Sleeper and ESPN render the same way."""
from __future__ import annotations

from dataclasses import dataclass, field


def player_key(name: str, position: str) -> str:
    """Cross-platform identity (names + position; IDs differ per platform)."""
    n = "".join(c for c in name.lower() if c.isalnum())
    for suffix in ("jr", "sr", "iii", "ii", "iv"):
        if n.endswith(suffix) and len(n) > len(suffix) + 3:
            n = n[: -len(suffix)]
            break
    pos = {"D/ST": "DEF", "DST": "DEF", "PK": "K"}.get(position.upper(), position.upper())
    return f"{n}|{pos}"


@dataclass(eq=False)  # compare players by identity
class Player:
    name: str
    position: str
    team: str  # NFL team abbrev, e.g. "KC"; "FA" if none
    slot: str  # lineup slot: "QB", "FLEX", "BN", "IR", "TAXI", ...
    injury: str = ""  # "Questionable", "Out", "IR", ...
    bye_week: int | None = None
    points: float | None = None  # this week's points, if known
    pid: str = ""  # Sleeper player id (also filled in for ESPN players by name match)
    age: int | None = None
    proj: float = 0.0  # projected points this week (league scoring)
    ros: float = 0.0  # projected points rest of season (league scoring)

    @property
    def is_starter(self) -> bool:
        return self.slot not in ("BN", "IR", "TAXI")

    @property
    def key(self) -> str:
        return player_key(self.name, self.position)


@dataclass
class Warning:
    level: str  # "danger" or "caution"
    message: str


@dataclass
class Matchup:
    my_points: float
    opp_name: str
    opp_points: float


@dataclass
class Team:
    name: str
    players: list[Player]
    is_me: bool = False


@dataclass
class League:
    platform: str  # "Sleeper" or "ESPN"
    name: str
    league_type: str  # redraft / keeper / dynasty
    week: int
    team_name: str = ""
    wins: int = 0
    losses: int = 0
    ties: int = 0
    points_for: float = 0.0
    standing: int | None = None
    num_teams: int = 0
    matchup: Matchup | None = None
    players: list[Player] = field(default_factory=list)
    empty_slots: list[str] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    error: str = ""
    url: str = ""
    # player_keys rostered by ANY team in the league (to know who's on waivers)
    rostered: set[str] = field(default_factory=set)
    starting_slots: list[str] = field(default_factory=list)  # e.g. QB, RB, RB, ..., SFLEX
    teams: list[Team] = field(default_factory=list)  # every team incl. mine
    scoring: str = "ppr"  # ppr | half | std
    te_premium: float = 0.0  # extra points per TE reception
    league_id: str = ""
    raw_scoring: dict = field(default_factory=dict)  # platform scoring settings (Sleeper keys)
    raw_positions: list[str] = field(default_factory=list)  # platform roster slots, incl. BN
    slug: str = ""

    def is_available(self, key: str) -> bool:
        return not self.error and key not in self.rostered

    @property
    def superflex(self) -> bool:
        return "SFLEX" in self.starting_slots or self.starting_slots.count("QB") > 1

    @property
    def record(self) -> str:
        r = f"{self.wins}-{self.losses}"
        return f"{r}-{self.ties}" if self.ties else r

    @property
    def starters(self) -> list[Player]:
        order = ["QB", "RB", "WR", "TE", "W/R", "W/T", "FLEX", "SFLEX", "K", "DEF"]
        return sorted(
            (p for p in self.players if p.is_starter),
            key=lambda p: order.index(p.slot) if p.slot in order else len(order),
        )

    @property
    def bench(self) -> list[Player]:
        return [p for p in self.players if not p.is_starter]
