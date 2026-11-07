"""Phone push notifications via ntfy.sh (free app for iPhone/Android, no account).

Anyone who knows your topic name can read/send to it, so treat NTFY_TOPIC like a
password: long and random, kept in .env / GitHub secrets.
"""
from __future__ import annotations

import requests

from .alerts import Alert

PRIORITY = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}
MAX_PER_RUN = 6


def send(alerts: list[Alert], topic: str, dashboard_url: str = "", dry_run: bool = False) -> int:
    if not alerts:
        return 0
    order = sorted(alerts, key=lambda a: -PRIORITY.get(a.priority, 3))
    batch, extra = order[:MAX_PER_RUN], order[MAX_PER_RUN:]
    if extra:
        batch.append(Alert(
            "summary", f"+{len(extra)} more updates",
            "\n".join(f"- {a.title}" for a in extra), "low", ["memo"], dashboard_url,
        ))
    for a in batch:
        payload = {
            "topic": topic,
            "title": a.title,
            "message": a.body,
            "priority": PRIORITY.get(a.priority, 3),
            "tags": a.tags,
        }
        click = a.url or dashboard_url
        if click:
            payload["click"] = click
        if dry_run or not topic:
            print(f"[{a.priority}] {a.title}\n    " + a.body.replace("\n", "\n    "))
            continue
        requests.post("https://ntfy.sh/", json=payload, timeout=15).raise_for_status()
    return len(batch)
