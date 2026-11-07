"""One scheduled run: refresh leagues + feeds, send phone alerts, build the static dashboard.

GitHub Actions runs this every 30 minutes. Locally:
    .venv\\Scripts\\python -m ffdash.job --dry-run --force
(--dry-run prints alerts instead of sending, --force ignores quiet hours)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "cache" / "state.json"
ET = ZoneInfo("America/New_York")
QUIET_START, QUIET_END = 1, 8  # no refreshes 1:00-7:59 AM Eastern


def in_quiet_hours(now: datetime) -> bool:
    return QUIET_START <= now.astimezone(ET).hour < QUIET_END


def _set_output(name: str, value: str) -> None:
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site", help="folder to write the static dashboard into")
    ap.add_argument("--dry-run", action="store_true", help="print alerts instead of sending them")
    ap.add_argument("--force", action="store_true", help="run even during quiet hours")
    args = ap.parse_args(argv)

    load_dotenv(ROOT / ".env")
    now = datetime.now(ET)
    if in_quiet_hours(now) and not args.force:
        print(f"Quiet hours ({now:%I:%M %p} ET): skipping.")
        _set_output("skipped", "true")
        return 0
    _set_output("skipped", "false")

    from . import feeds, notify, sleeper
    from .alerts import Alert, evaluate
    from .render import render_site
    from .service import build_dashboard

    dash = build_dashboard()
    db = sleeper.players_db()
    state = load_state()
    first_run = "injuries" not in state

    def safe(fn, default):
        try:
            return fn()
        except Exception as e:
            print(f"warning: {fn.__name__} feed failed: {e}", file=sys.stderr)
            return default

    injuries = safe(feeds.injuries, None)
    articles = safe(feeds.news, [])
    trending = safe(feeds.trending, [])

    prev_injuries = state.get("injuries")
    result = evaluate(dash.leagues, db, injuries or {}, articles, trending, state, now)
    if injuries is None and prev_injuries is not None:
        state["injuries"] = prev_injuries  # don't forget statuses because one fetch failed

    alerts = result.alerts
    dashboard_url = os.getenv("DASHBOARD_URL", "")
    if first_run:
        alerts = [Alert("setup", "Fantasy alerts are on",
                        f"Watching {len([l for l in dash.leagues if not l.error])} leagues. "
                        "You'll get pushes for injuries to your players, starters going down "
                        "(with the backup to grab), and hot waiver adds.", "default", ["tada"])]

    sent = notify.send(alerts, os.getenv("NTFY_TOPIC", "").strip(), dashboard_url, dry_run=args.dry_run)
    state["last_run"] = now.isoformat(timespec="minutes")
    save_state(state)

    render_site(Path(args.site), dash, state.get("log", []), result.waiver_ideas, now)
    print(f"{now:%a %I:%M %p} ET: {len(dash.leagues)} leagues, {len(result.alerts)} new alerts, "
          f"{sent} notifications {'printed' if args.dry_run else 'sent'}, site -> {args.site}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
