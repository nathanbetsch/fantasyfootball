"""Trade values from FantasyCalc (https://fantasycalc.com), tuned to each league.

FantasyCalc's values come from real trades and adjust for dynasty vs redraft,
1QB vs superflex, league size, and PPR, the same settings its trade calculator
uses. Its API has no TE-premium option, so TE values get a boost scaled to the
league's TE bonus (like KeepTradeCut's TE+ toggle). Falls back to Dynasty Daddy
values for dynasty leagues if FantasyCalc is down.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .models import League

CACHE = Path(__file__).resolve().parent.parent / "cache" / "values"
FC_URL = "https://api.fantasycalc.com/values/current?isDynasty={dyn}&numQbs={qbs}&numTeams={teams}&ppr={ppr}"
DD_URL = "https://dynasty-daddy.com/api/v1/player/all/today"
TTL = 6 * 3600


@dataclass
class LeagueValues:
    values: dict[str, float]  # sleeper_id -> trade value
    source: str  # shown on the page, e.g. "FantasyCalc · Dynasty · Superflex · 12 teams · PPR"
    te_boost: float = 1.0
    calculator: str = "fc"  # "fc" = FantasyCalc-style package math, "dd" = Dynasty Daddy's
    ranks: dict[str, int] | None = None  # sleeper_id -> overall value rank (Dynasty Daddy)

    def get(self, pid: str, position: str) -> float:
        v = self.values.get(pid, 0.0)
        return v * self.te_boost if position == "TE" else v


def _cached_json(name: str, url: str):
    path = CACHE / name
    if path.exists() and time.time() - path.stat().st_mtime < TTL:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "personal-fantasy-dashboard"})
        r.raise_for_status()
        data = r.json()
    except Exception:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


DD_INFUSED_URL = "https://dynasty-daddy.com/api/v1/player/all/today?market=14"
DD_SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "REC_FLEX", "WRRB_FLEX", "SUPER_FLEX",
            "K", "DF", "LB", "DB", "DL", "IDP_FLEX"]


def dynasty_daddy_values(league: League) -> LeagueValues | None:
    """Dynasty Daddy 'league-infused' values: its trade calculator re-values every
    player for this league's exact lineup slots, team count and scoring settings
    (PPR, TE premium, bonuses...), the same as linking the league on dynasty-daddy.com."""
    if not league.raw_positions or not league.raw_scoring:
        return None
    fmt = {"teamCount": league.num_teams, **{k: league.raw_positions.count(k) for k in DD_SLOTS}}
    path = CACHE / f"dd-infused-{league.league_id}.json"
    data = None
    if path.exists() and time.time() - path.stat().st_mtime < TTL:
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        try:
            r = requests.post(DD_INFUSED_URL, json={"format": fmt, "settings": league.raw_scoring}, timeout=60,
                              headers={"User-Agent": "personal-fantasy-dashboard"})
            r.raise_for_status()
            data = r.json()
            CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if not data:
        return None
    sf = league.superflex
    vals = {}
    for row in data:
        if not row.get("sleeper_id"):
            continue
        v = row.get("sf_trade_value") if sf else (row.get("trade_value") or row.get("sf_trade_value"))
        vals[str(row["sleeper_id"])] = float(v or 0)
    ranks = {pid: i for i, pid in enumerate(sorted(vals, key=vals.get, reverse=True))}
    label = " · ".join(filter(None, [
        "League-infused values", "Superflex" if sf else "1QB", f"{league.num_teams} teams",
        {"ppr": "PPR", "half": "Half PPR", "std": "Standard"}[league.scoring],
        f"TE premium +{league.te_premium:g}" if league.te_premium else "",
    ]))
    return LeagueValues(vals, f"Dynasty Daddy trade calculator · {label}", 1.0, "dd", ranks)


def for_league(league: League) -> LeagueValues | None:
    # Dynasty leagues on Sleeper use Dynasty Daddy's calculator with the league's settings
    if league.league_type == "dynasty" and league.platform == "Sleeper":
        dd = dynasty_daddy_values(league)
        if dd:
            return dd
    dynasty = league.league_type in ("dynasty", "keeper")
    qbs = 2 if league.superflex else 1
    teams = league.num_teams or 12
    ppr = {"ppr": 1, "half": 0.5, "std": 0}[league.scoring]
    te_boost = 1 + 0.6 * league.te_premium  # +0.25/catch -> TE values x1.15; +0.5 -> x1.30

    label = " · ".join(filter(None, [
        "Dynasty" if dynasty else "Redraft", "Superflex" if qbs == 2 else "1QB", f"{teams} teams",
        {"ppr": "PPR", "half": "Half PPR", "std": "Standard"}[league.scoring],
        f"TE premium +{league.te_premium:g}" if league.te_premium else "",
    ]))

    data = _cached_json(f"fc-{int(dynasty)}-{qbs}-{teams}-{ppr}.json",
                        FC_URL.format(dyn=str(dynasty).lower(), qbs=qbs, teams=teams, ppr=ppr))
    if data:
        vals = {str(row["player"]["sleeperId"]): float(row["value"])
                for row in data if row.get("player", {}).get("sleeperId")}
        return LeagueValues(vals, f"FantasyCalc · {label}", te_boost)

    if dynasty:
        dd = _cached_json("dynasty-daddy.json", DD_URL)
        if dd:
            key = "sf_trade_value" if qbs == 2 else "trade_value"
            vals = {str(r["sleeper_id"]): float(r.get(key) or 0) for r in dd if r.get("sleeper_id")}
            return LeagueValues(vals, f"Dynasty Daddy · {label}", te_boost)
    return None
