"""Per-league advice: start/sit fixes for this week, trade offers to request, waiver targets.

Values come from Sleeper's rest-of-season projections in each league's scoring
(dynasty leagues also weight age). A trade is suggested only when:
  - YOUR best lineup gets meaningfully better,
  - THEIR best lineup doesn't get worse (so they have a reason to say yes), and
  - the "market value" they receive is close to what they give up (it looks fair).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from .models import League, Player, player_key
from .projections import Projections
from .values import LeagueValues

SKILL = ("QB", "RB", "WR", "TE")
ELIGIBLE = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"}, "DEF": {"DEF"},
    "W/R": {"RB", "WR"}, "W/T": {"WR", "TE"}, "FLEX": {"RB", "WR", "TE"},
    "SFLEX": {"QB", "RB", "WR", "TE"},
}
FILL_ORDER = ["QB", "RB", "WR", "TE", "K", "DEF", "W/R", "W/T", "FLEX", "SFLEX"]
OUT = {"Out", "IR", "Sus", "PUP", "NA"}
PEAK_AGE = {"QB": 28, "RB": 24, "WR": 26, "TE": 27}


# --- lineup math ---------------------------------------------------------------

def best_lineup(players: list[Player], slots: list[str], val) -> list[tuple[str, Player]]:
    pool = sorted((p for p in players if p.slot not in ("IR", "TAXI")), key=val, reverse=True)
    used: set[int] = set()
    lineup = []
    for slot in sorted(slots, key=lambda s: FILL_ORDER.index(s) if s in FILL_ORDER else 99):
        ok = ELIGIBLE.get(slot, {slot})
        pick = next((p for p in pool if id(p) not in used and p.position in ok), None)
        if pick:
            used.add(id(pick))
            lineup.append((slot, pick))
    return lineup


def week_val(p: Player) -> float:
    if p.injury in OUT:
        return 0.0
    return p.proj * (0.25 if p.injury == "Doubtful" else 1.0)


# --- this week's start/sit -------------------------------------------------------

@dataclass
class LineupFix:
    start: Player
    bench: Player | None
    slot: str
    gain: float


def lineup_fixes(league: League) -> list[LineupFix]:
    me = league.players
    slots = league.starting_slots
    best = best_lineup(me, slots, week_val)
    best_ids = {id(p) for _, p in best}
    current = [p for p in league.starters]
    cur_ids = {id(p) for p in current}
    ins = [(s, p) for s, p in best if id(p) not in cur_ids and not (p.points or 0) > 0]
    outs = sorted((p for p in current if id(p) not in best_ids), key=week_val)
    fixes = []
    for slot, p in ins:
        partner = next((o for o in outs if o.position in ELIGIBLE.get(slot, {slot})), outs[0] if outs else None)
        if partner:
            outs.remove(partner)
        gain = week_val(p) - (week_val(partner) if partner else 0.0)
        if gain >= 0.5:
            fixes.append(LineupFix(p, partner, slot, round(gain, 1)))
    return fixes


# --- trades ----------------------------------------------------------------------

@dataclass
class TradeIdea:
    team: str
    give: list[Player]
    get: list[Player]
    give_value: int  # trade-calculator totals (package-adjusted)
    get_value: int
    my_gain_pct: float  # % change in your team value (best lineup + some bench)
    their_gain_pct: float
    my_pts: float  # projected pts/week change for your best lineup, rest of season
    why_me: str
    fairness: str  # "Fair" / "You pay a bit more"


class TradeEngine:
    """Finds trades that look fair on a trade calculator but fit your roster better."""

    def __init__(self, league: League, proj: Projections, values: LeagueValues | None):
        self.lg = league
        self.weeks = proj.weeks_left
        self.values = values
        self.source = values.source if values else "Sleeper rest-of-season projections"

    def value(self, p: Player) -> float:
        if self.values:
            return self.values.get(p.pid, p.position)
        # Fallback without a values site: rest-of-season points, age-weighted in dynasty
        if self.lg.league_type == "dynasty" and p.age and p.position in PEAK_AGE:
            return p.ros * min(1.4, max(0.6, 1 + 0.06 * (PEAK_AGE[p.position] - p.age)))
        return p.ros

    def package(self, players: list[Player], top: float) -> float:
        """Calculator-style package value: the best piece counts fully; extra pieces are
        discounted the further they are below the best player in the deal (so 2 mid
        players don't equal 1 star)."""
        vals = sorted((self.value(p) for p in players), reverse=True)
        if not vals or top <= 0:
            return 0.0
        return vals[0] + sum(v * (0.45 + 0.55 * v / top) for v in vals[1:])

    def evaluate(self, give: list[Player], get: list[Player]):
        """(your side's value, their side's value, verdict) or None if not acceptable."""
        if self.values and self.values.calculator == "dd":
            return self._dynasty_daddy(give, get)
        top = max(self.value(p) for p in give + get)
        v_give, v_get = self.package(give, top), self.package(get, top)
        # Must look fair on a calculator: you give 95-115% of what you get
        if v_get <= 0 or not (0.95 * v_get <= v_give <= 1.15 * v_get):
            return None
        return v_give, v_get, "Fair" if v_give <= 1.05 * v_get else "You pay a bit more"

    # --- Dynasty Daddy's trade calculator, mirrored from dynasty-daddy.com ----------
    def _dd_multiplier(self, stud: Player, other_side: list[Player]) -> float:
        """Stud bonus shrinks 20% for each player on the other side who is close to
        the stud in the overall value ranks (within 5 spots for a top-10 player, else 20)."""
        ranks = self.values.ranks or {}
        rank = lambda p: ranks.get(p.pid, 9999)
        m = 1.0
        for p in other_side:
            if self.value(stud) * 0.95 > self.value(p) and abs(rank(stud) - rank(p)) <= (5 if rank(stud) < 10 else 20):
                m -= 0.2
        return m

    def _dd_stud(self, side1: list[Player], side2: list[Player]):
        o = sorted(side1, key=self.value, reverse=True)
        s = sorted(side2, key=self.value, reverse=True)
        while o and s:
            a, b = o[0], s[0]
            if self.value(a) > self.value(b):
                if self.value(a) * 0.95 <= self.value(b):
                    o.pop(0); s.pop(0)
                else:
                    return a, self._dd_multiplier(a, side2)
            else:
                if self.value(b) * 0.95 <= self.value(a):
                    o.pop(0); s.pop(0)
                else:
                    return b, self._dd_multiplier(b, side1)
        return (o[0], 1.0) if o else (None, 1.0)

    def _dynasty_daddy(self, give: list[Player], get: list[Player]):
        t1 = sum(self.value(p) for p in give)  # team 1 = you
        t2 = sum(self.value(p) for p in get)
        total = t1 + t2
        if t1 <= 0 or t2 <= 0:
            return None
        stud, mult = self._dd_stud(give, get)
        adj, side = 0.0, 1
        if stud is not None:
            side = 2 if stud in get else 1
            adj = round(round(self.value(stud) / total * (t2 if side == 1 else t1)) * mult)
        v1 = t1 + (adj if side == 1 else 0)
        v2 = t2 + (adj if side == 2 else 0)
        buffer = (total + adj) * 0.05  # Dynasty Daddy calls it even inside a 5% buffer
        diff = v1 - v2  # > 0 means you're giving more
        if abs(diff) < buffer:
            return v1, v2, "Fair"
        if 0 < diff <= 2 * buffer:
            return v1, v2, "You pay a bit more"
        return None

    def strength(self, players: list[Player]) -> float:
        lineup = best_lineup(players, self.lg.starting_slots, self.value)
        used = {id(p) for _, p in lineup}
        bench = sorted((self.value(p) for p in players if id(p) not in used and p.position in SKILL), reverse=True)
        return sum(self.value(p) for _, p in lineup) + 0.2 * sum(bench[:4])

    def _proj_lineup(self, players: list[Player]) -> float:
        return sum(p.ros for _, p in best_lineup(players, self.lg.starting_slots, lambda p: p.ros))

    def ideas(self, limit: int = 4) -> list[TradeIdea]:
        mine = next((t for t in self.lg.teams if t.is_me), None)
        if not mine:
            return []
        my_players = mine.players
        base_me = self.strength(my_players)
        base_me_pts = self._proj_lineup(my_players)
        tradable = lambda ps: sorted((p for p in ps if p.position in SKILL and self.value(p) > 0),
                                     key=self.value, reverse=True)
        my_assets = tradable(my_players)[:14]
        results: list[tuple[float, TradeIdea]] = []

        for team in self.lg.teams:
            if team.is_me:
                continue
            theirs = team.players
            base_them = self.strength(theirs)
            their_assets = tradable(theirs)[:12]
            packages = (
                [([a], [c]) for a in my_assets for c in their_assets]
                + [([a, b], [c]) for a, b in combinations(my_assets[:10], 2) for c in their_assets[:8]]
                + [([a], [c, d]) for a in my_assets[:8] for c, d in combinations(their_assets[:10], 2)]
            )
            best = None
            for give, get in packages:
                verdict = self.evaluate(give, get)
                if verdict is None:
                    continue
                v_give, v_get, fairness = verdict
                me_after = [p for p in my_players if p not in give] + get
                dm = self.strength(me_after) - base_me
                if dm < max(1.0, 0.003 * base_me):
                    continue
                them_after = [p for p in theirs if p not in get] + give
                dt = self.strength(them_after) - base_them
                # The calculator says it's even; their lineup can't drop more than a hair
                if dt < -0.005 * base_them:
                    continue
                score = dm + 0.4 * dt - 0.5 * max(0.0, v_give - v_get)
                if best is None or score > best[0]:
                    lu = best_lineup(me_after, self.lg.starting_slots, self.value)
                    starts = [f"{p.name} starts at {slot}" for slot, p in lu if p in get]
                    best = (score, TradeIdea(
                        team.name, give, get, round(v_give), round(v_get),
                        round(100 * dm / base_me, 1), round(100 * dt / base_them, 1) if base_them else 0.0,
                        round((self._proj_lineup(me_after) - base_me_pts) / self.weeks, 1),
                        "; ".join(starts) or "Adds depth",
                        fairness,
                    ))
            if best:
                results.append(best)

        results.sort(key=lambda r: -r[0])
        return [idea for _, idea in results[:limit]]


# --- waivers ---------------------------------------------------------------------

@dataclass
class WaiverTarget:
    name: str
    position: str
    team: str
    ros_per_week: float
    proj: float
    trending: int | None = None  # Sleeper adds, if trending
    needed: bool = False
    tags: list[str] = field(default_factory=list)


def waiver_targets(league: League, proj: Projections, trending: dict[str, int], need_fn,
                   limit: int = 6) -> list[WaiverTarget]:
    idx = 0 if league.scoring == "ppr" else 1 if league.scoring == "half" else 2
    out = []
    for pid, pts in proj.ros.items():
        info = proj.db.get(pid)
        if not info or info.get("pos") not in SKILL or info.get("team") in (None, "", "FA"):
            continue
        if info.get("injury") in OUT or player_key(info["name"], info["pos"]) in league.rostered:
            continue
        wk = proj.this_week.get(pid)
        out.append(WaiverTarget(
            info["name"], info["pos"], info["team"],
            round(pts[idx] / proj.weeks_left, 1), round(wk[idx], 1) if wk else 0.0,
            trending.get(pid), bool(need_fn(league, info["pos"])),
        ))
    # Rank: rest-of-season value, bumped for trending and for positions you need
    out.sort(key=lambda w: -(w.ros_per_week * (1.25 if w.needed else 1) + (2 if w.trending else 0)))
    return out[:limit]
