"""Local preview of the fantasy site (same pages GitHub publishes).

Run:  .venv\\Scripts\\python app.py   (or double-click run.bat)
Pages rebuild at most every 2 minutes; add ?refresh=1 to force it.
"""
from __future__ import annotations

import os
import socket
import time
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, abort, redirect, request

load_dotenv()

from ffdash import cache, feeds, sleeper  # noqa: E402
from ffdash.job import ET, load_state  # noqa: E402
from ffdash.projections import Projections  # noqa: E402
from ffdash.render import build_pages  # noqa: E402
from ffdash.service import build_dashboard  # noqa: E402

app = Flask(__name__)
_pages: dict[str, str] = {}
_built = 0.0


def pages() -> dict[str, str]:
    global _pages, _built
    if _pages and time.time() - _built < 120:
        return _pages
    dash = build_dashboard()
    db = sleeper.players_db()
    proj = Projections(int(os.getenv("SEASON", "2026")), dash.week or 1, db)
    for lg in dash.leagues:
        if not lg.error:
            proj.enrich(lg)
    state = load_state()  # read-only here: alerts log + news archive from the last job run
    try:
        articles, trending = feeds.news(), feeds.trending()
    except Exception:
        articles, trending = [], []
    _pages = build_pages(dash, db, proj, state, articles, trending, datetime.now(ET), static=False)
    _built = time.time()
    return _pages


@app.route("/")
@app.route("/<name>")
def page(name: str = "index.html"):
    if request.args.get("refresh"):
        global _built
        cache.clear()
        _built = 0
        return redirect(request.path)
    html = pages().get(name)
    if html is None:
        abort(404)
    return html


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    print(f"\n  On this PC:             http://127.0.0.1:{port}")
    if host == "0.0.0.0":
        print(f"  On your phone (Wi-Fi):  http://{lan_ip()}:{port}\n")
    app.run(host=host, port=port, debug=False)
