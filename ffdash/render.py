"""Render the dashboard to a self-contained static index.html (for GitHub Pages)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).resolve().parent


def fmt_pts(v):
    return "–" if v is None else f"{v:.1f}"


def fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%a %I:%M %p").replace(" 0", " ")
    except (TypeError, ValueError):
        return iso or ""


def environment() -> Environment:
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape())
    env.filters["pts"] = fmt_pts
    env.filters["when"] = fmt_time
    return env


def render_site(out_dir: Path, dash, alert_log: list[dict], waiver_ideas, now: datetime) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    html = environment().get_template("dashboard.html").render(
        dash=dash,
        alerts=alert_log,
        waiver_ideas=waiver_ideas,
        inline_css=(HERE / "static" / "style.css").read_text(encoding="utf-8"),
        css_href=None,
        refresh_href=None,
        updated=now.strftime("%a %I:%M %p ET").replace(" 0", " "),
    )
    path = out_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return path
