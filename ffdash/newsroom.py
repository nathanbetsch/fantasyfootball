"""The News page: a rolling 48-hour archive of ESPN NFL stories, ranked into
the top fantasy-impact stories and a couple of the biggest general NFL stories."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from .feeds import Article
from .models import League, player_key

WINDOW = timedelta(hours=48)
FANTASY_WORDS = re.compile(
    r"injur|ruled out|out for|\bout\b|torn|acl|achilles|hamstring|ankle|concussion|surgery|"
    r"\bir\b|injured reserve|placed on|activated|return|suspend|trade[ds]?\b|acquir|releas|"
    r"waive|bench|named (the )?starter|to start|will start|starting|depth chart|demot|promot|"
    r"workload|snaps|questionable|doubtful|fantasy|waiver|sign(s|ed|ing)\b",
    re.I,
)


@dataclass
class Story:
    id: str
    headline: str
    description: str
    url: str
    published: str
    athletes: list[str]
    kind: str = ""
    impact: list[str] = field(default_factory=list)  # "On your roster in We Cummin", ...
    score: float = 0.0


def update_archive(state: dict, articles: list[Article], now: datetime) -> list[dict]:
    archive = {a["id"]: a for a in state.get("news_archive", [])}
    for a in articles:
        archive.setdefault(a.id, {
            "id": a.id, "headline": a.headline, "description": a.description, "url": a.url,
            "published": a.published, "athletes": a.athletes, "kind": a.kind,
        })
    cutoff = now - WINDOW
    keep = [a for a in archive.values() if _when(a["published"]) >= cutoff]
    keep.sort(key=lambda a: a["published"], reverse=True)
    state["news_archive"] = keep[:200]
    return state["news_archive"]


def _when(iso: str) -> datetime:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def rank(archive: list[dict], leagues: list[League], db: dict, ros_ppr: dict[str, list[float]],
         weeks_left: int, now: datetime) -> tuple[list[Story], list[Story]]:
    """Returns (top fantasy stories, top other NFL stories)."""
    # name -> fantasy relevance (rest-of-season points per week)
    relevance: dict[str, float] = {}
    position: dict[str, str] = {}
    for pid, p in db.items():
        if p.get("pos") in ("QB", "RB", "WR", "TE") and pid in ros_ppr:
            n = player_key(p["name"], "").split("|")[0]
            v = ros_ppr[pid][0] / weeks_left
            if v > relevance.get(n, -1):
                relevance[n], position[n] = v, p["pos"]

    ok = [lg for lg in leagues if not lg.error]
    mine = {}
    for lg in ok:
        for p in lg.players:
            mine.setdefault(player_key(p.name, "").split("|")[0], []).append((lg, p))

    stories = []
    for a in archive:
        s = Story(**{k: a.get(k, "") for k in ("id", "headline", "description", "url", "published", "kind")},
                  athletes=a.get("athletes", []))
        text = f"{s.headline} {s.description}"
        tagged = [player_key(n, "").split("|")[0] for n in s.athletes]
        rel = sum(min(relevance.get(n, 0) / 15, 1.5) for n in tagged)
        rel = min(rel, 2.5)
        score = rel * (1.5 if FANTASY_WORDS.search(text) else 0.5)
        if "fantasy" in s.headline.lower():
            score += 0.8
        age_h = (now - _when(s.published)).total_seconds() / 3600
        score *= 1.25 if age_h < 12 else 1.0 if age_h < 24 else 0.8
        if any(n in mine for n in tagged):
            score *= 1.4
        for name, n in zip(s.athletes, tagged):
            if n in mine:
                spots = mine[n]
                s.impact.append(f"{name}: on your roster in " + ", ".join(
                    f"{lg.name}{' (starting)' if p.is_starter else ''}" for lg, p in spots))
            elif relevance.get(n, 0) >= 6:
                key = player_key(name, position[n])
                free = [lg.name for lg in ok if key not in lg.rostered]
                if free:
                    s.impact.append(f"{name}: available in " + ", ".join(free))
        s.impact.sort(key=lambda line: "on your roster" not in line)
        s.impact = s.impact[:3]
        s.score = round(score, 2)
        stories.append(s)

    fantasy = sorted((s for s in stories if s.score >= 0.6), key=lambda s: -s.score)[:3]
    picked = {s.id for s in fantasy}
    general = [s for s in stories if s.id not in picked and "fantasy" not in s.headline.lower()]
    # biggest general stories: ESPN's headline items first, then the most recent
    general.sort(key=lambda s: (s.kind != "HeadlineNews", -_when(s.published).timestamp()))
    return fantasy, general[:2]
