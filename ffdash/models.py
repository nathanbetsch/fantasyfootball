"""Platform-neutral data shapes so Sleeper and ESPN render the same way."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Player:
    name: str
    position: str
    team: str  # NFL team abbrev, e.g. "KC"; "FA" if none
    slot: str  # lineup slot: "QB", "FLEX", "BN", "IR", "TAXI", ...
    injury: str = ""  # "Questionable", "Out", "IR", ...
    bye_week: int | None = None
    points: float | None = None  # this week's points, if known

    @property
    def is_starter(self) -> bool:
        return self.slot not in ("BN", "IR", "TAXI")

    @property
    def key(self) -> str:
        """Cross-platform identity (names + position; IDs differ per platform)."""
        n = "".join(c for c in self.name.lower() if c.isalnum())
        for suffix in ("jr", "sr", "ii", "iii", "iv"):
            if n.endswith(suffix) and len(n) > len(suffix) + 3:
                n = n[: -len(suffix)]
                break
        return f"{n}|{self.position}"


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
