"""Render the 4-page site (News + one page per league) to HTML strings."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .advisor import TradeEngine, lineup_fixes, waiver_targets
from .alerts import need
from .newsroom import rank, update_archive
from .values import for_league

HERE = Path(__file__).resolve().parent


def fmt_pts(v):
    return "–" if v is None else f"{v:.1f}"


def fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%a %I:%M %p").replace(" 0", " ")
    except (TypeError, ValueError):
        return iso or ""


def fmt_ago(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return ""
    mins = int((datetime.now(timezone.utc) - t).total_seconds() // 60)
    if mins < 60:
        return f"{max(mins, 1)}m ago"
    if mins < 48 * 60:
        return f"{mins // 60}h ago"
    return f"{mins // 1440}d ago"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "league"


def environment() -> Environment:
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape())
    env.filters["pts"] = fmt_pts
    env.filters["when"] = fmt_time
    env.filters["ago"] = fmt_ago
    return env


def build_pages(dash, db, proj, state: dict, articles, trending, now: datetime,
                static: bool = True) -> dict[str, str]:
    """Returns {filename: html}. `state` gets the updated 48h news archive."""
    env = environment()
    css = (HERE / "static" / "apple.css").read_text(encoding="utf-8")
    updated = now.strftime("%a %I:%M %p ET").replace(" 0", " ")

    for lg in dash.leagues:
        lg.slug = slugify(lg.name)
    files = {"news": "index.html", **{lg.slug: f"{lg.slug}.html" for lg in dash.leagues}}

    def tabs(active: str):
        return [{"href": files["news"], "label": "News", "icon": "news", "active": active == "news"}] + [
            {"href": files[lg.slug], "label": lg.name, "icon": "league", "active": active == lg.slug}
            for lg in dash.leagues
        ]

    common = dict(css=css, updated=updated, static=static, week=dash.week)
    pages: dict[str, str] = {}

    archive = update_archive(state, articles, now)
    fantasy, general = rank(archive, dash.leagues, db, proj.ros, proj.weeks_left, now)
    pages["index.html"] = env.get_template("news.html").render(
        **common, tabs=tabs("news"), fantasy=fantasy, general=general, alerts=state.get("log", []),
    )

    trend = {t.sleeper_id: t.count for t in trending}
    for lg in dash.leagues:
        ctx = dict(lg=lg, fixes=[], trades=[], waivers=[], weeks_left=proj.weeks_left, value_source="")
        if not lg.error:
            ctx["fixes"] = lineup_fixes(lg)
            engine = TradeEngine(lg, proj, for_league(lg))
            ctx["trades"] = engine.ideas()
            ctx["value_source"] = engine.source
            ctx["waivers"] = waiver_targets(lg, proj, trend, need)
        pages[files[lg.slug]] = env.get_template("league.html").render(**common, tabs=tabs(lg.slug), **ctx)
    return pages


def write_site(out_dir: Path, pages: dict[str, str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.html"):
        if old.name not in pages:
            old.unlink()
    for name, html in pages.items():
        (out_dir / name).write_text(html, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
