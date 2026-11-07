"""Decide what's worth a phone alert by comparing this run's feeds with the last run.

Alerts fire only on CHANGES, so the same news never buzzes your phone twice:
  1. One of YOUR players gets worse on the injury report
  2. An NFL starter (QB/RB/TE, top-2 WR) goes Doubtful/Out/IR -> his backup, if he's
     on waivers in any of your leagues (flagged urgent when you actually need him)
  3. A player blows up on Sleeper's trending-adds list and is available to you
  4. A news story tags one of your players
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from .feeds import SEVERITY, SKILL, Article, Injury, Trending
from .models import League, player_key

BAD = SEVERITY["Doubtful"]  # Doubtful or worse = plan on him not playing
DANGER_SLEEPER = {"Out", "IR", "Doubtful", "Sus", "PUP"}


@dataclass
class Alert:
    kind: str  # my_player | backup | trending | news
    title: str
    body: str
    priority: str = "default"  # min | low | default | high | urgent
    tags: list[str] = field(default_factory=list)
    url: str = ""
    time: str = ""


@dataclass
class WaiverIdea:
    name: str
    position: str
    team: str
    reason: str
    leagues: list[str]


@dataclass
class Result:
    alerts: list[Alert]
    waiver_ideas: list[WaiverIdea]


def _db_index(db: dict[str, dict]) -> dict[str, dict]:
    idx = {}
    for pid, p in db.items():
        if p.get("pos") in SKILL and p.get("team") not in (None, "", "FA"):
            idx[player_key(p["name"], p["pos"])] = {**p, "id": pid}
    return idx


def _backups(hurt: dict, db: dict[str, dict], injuries: dict[str, Injury]) -> list[dict]:
    """Next player(s) on the same team's depth chart at the same spot."""
    def healthy(p) -> bool:
        inj = injuries.get(player_key(p["name"], p["pos"]))
        return inj is None or inj.severity < BAD

    # Sleeper often already moved the hurt player down the depth chart, so "replacement"
    # = the highest healthy player at his spot on that team other than him.
    def same_spot(p) -> bool:
        if hurt["pos"] != "WR":
            return True
        return p.get("depth_pos") == hurt.get("depth_pos") or not hurt.get("depth_pos")

    cands = [
        {**p, "id": pid} for pid, p in db.items()
        if pid != hurt["id"] and p.get("team") == hurt["team"] and p.get("pos") == hurt["pos"]
        and isinstance(p.get("depth"), int) and same_spot(p) and healthy(p)
    ]
    cands.sort(key=lambda p: p["depth"])
    return cands[:1]


def _matters(hurt: dict, key: str, leagues: list[League]) -> bool:
    """Was this a starter worth replacing? (Near the top of the depth chart, and
    either the clear #1 or someone rostered in one of your leagues.)"""
    d = hurt.get("depth")
    if not isinstance(d, int) or d > (3 if hurt["pos"] == "WR" else 2):
        return False
    return d == 1 or any(key in lg.rostered for lg in leagues)


def need(league: League, pos: str) -> str:
    """Why this league needs a player at `pos` this week ('' if it doesn't)."""
    mine = [p for p in league.players if p.position == pos]
    healthy = [p for p in mine if p.injury not in DANGER_SLEEPER and p.bye_week != league.week]
    hurt_starters = [p for p in league.starters if p.position == pos and p not in healthy]
    if hurt_starters:
        p = hurt_starters[0]
        why = "on BYE" if p.bye_week == league.week else p.injury
        return f"your starter {p.name} is {why}"
    slots = league.starting_slots.count(pos)
    if pos == "QB" and league.superflex:
        slots = max(slots, 2)
    if len(healthy) < slots:
        return f"you only have {len(healthy)} healthy {pos}{'s' if len(healthy) != 1 else ''}"
    return ""


def evaluate(leagues: list[League], db: dict[str, dict], injuries: dict[str, Injury],
             articles: list[Article], trending: list[Trending], state: dict,
             now: datetime) -> Result:
    ok = [lg for lg in leagues if not lg.error]
    idx = _db_index(db)
    alerts: list[Alert] = []
    prev_inj: dict[str, str] = state.get("injuries", {})
    first_run = "injuries" not in state

    my_keys = {p.key: [] for lg in ok for p in lg.players}
    for lg in ok:
        for p in lg.players:
            my_keys[p.key].append((lg, p))

    # --- 1 & 2: injury report changes -------------------------------------
    for key, inj in injuries.items():
        before = SEVERITY.get(prev_inj.get(key, "Active"), 0)
        if first_run or inj.severity <= before or inj.severity == 0:
            continue

        if key in my_keys:
            spots = my_keys[key]
            starting = [lg.name for lg, p in spots if p.is_starter]
            where = ", ".join(f"{lg.name} ({'starting' if p.is_starter else p.slot.lower()})" for lg, p in spots)
            alerts.append(Alert(
                "my_player",
                f"{inj.name} ({inj.position}, {inj.team}) is now {inj.short}",
                f"You have him in: {where}."
                + (" Swap him out of your lineup before kickoff." if starting and inj.severity >= BAD else "")
                + (f"\n{inj.comment}" if inj.comment else ""),
                "high" if starting and inj.severity >= BAD else "default",
                ["warning"],
            ))

        hurt = idx.get(key)
        if inj.severity >= BAD and hurt and _matters(hurt, key, ok):
            for b in _backups(hurt, db, injuries):
                bkey = player_key(b["name"], b["pos"])
                avail = [lg for lg in ok if lg.is_available(bkey)]
                if not avail:
                    continue
                needs = {lg.name: need(lg, b["pos"]) for lg in avail}
                urgent = [n for n, why in needs.items() if why]
                lines = [f"- {n}: {'PICK UP, ' + why if why else 'available (depth / stash)'}" for n, why in needs.items()]
                alerts.append(Alert(
                    "backup",
                    f"{inj.name} {inj.short} -> pick up {b['name']} ({b['pos']}, {b['team']})",
                    f"{b['name']} is next on the {b['team']} depth chart and is on waivers in:\n" + "\n".join(lines),
                    "high" if urgent else "default",
                    ["rotating_light" if urgent else "football"],
                ))

    # --- 3: trending adds you can actually get ----------------------------
    seen_trend: dict[str, str] = state.get("trending_alerted", {})
    cutoff = (now - timedelta(days=3)).isoformat()
    hot = []
    ideas: list[WaiverIdea] = []
    for rank, t in enumerate(trending):
        p = db.get(t.sleeper_id)
        if not p or p.get("pos") not in SKILL or p.get("injury") in DANGER_SLEEPER:
            continue
        key = player_key(p["name"], p["pos"])
        avail = [lg for lg in ok if lg.is_available(key)]
        if not avail:
            continue
        needy = [lg.name for lg in avail if need(lg, p["pos"])]
        ideas.append(WaiverIdea(p["name"], p["pos"], p.get("team", "FA"),
                                f"#{rank + 1} most-added on Sleeper ({t.count:,} adds)"
                                + (f"; fills a need in {', '.join(needy)}" if needy else ""),
                                [lg.name for lg in avail]))
        if rank < 10 and seen_trend.get(key, "") < cutoff and not first_run:
            hot.append((p, t, avail))
            seen_trend[key] = now.isoformat()
    state["trending_alerted"] = {k: v for k, v in seen_trend.items() if v >= cutoff}
    if hot:
        alerts.append(Alert(
            "trending",
            "Hot waiver adds available to you",
            "\n".join(f"- {p['name']} ({p['pos']}, {p.get('team', 'FA')}): {t.count:,} adds; "
                      f"free in {', '.join(lg.name for lg in avail)}" for p, t, avail in hot[:5]),
            "default", ["chart_with_upwards_trend"],
        ))

    # --- 4: news about your players --------------------------------------
    seen_news = set(state.get("news_seen", []))
    my_names = {k.split("|")[0]: k for k in my_keys}
    for a in articles:
        if a.id in seen_news:
            continue
        seen_news.add(a.id)
        if first_run:
            continue
        tagged = [n for n in a.athletes if player_key(n, "").split("|")[0] in my_names]
        if tagged:
            alerts.append(Alert("news", f"News: {', '.join(tagged)}", a.headline, "low", ["newspaper"], a.url))
    state["news_seen"] = [a.id for a in articles]  # only need to remember what's still in the feed

    # --- remember for next run --------------------------------------------
    state["injuries"] = {k: i.status for k, i in injuries.items() if i.severity > 0}
    stamp = now.isoformat(timespec="minutes")
    for al in alerts:
        al.time = stamp
    log = [asdict(a) for a in alerts] + state.get("log", [])
    state["log"] = log[:40]
    return Result(alerts, ideas[:12])
