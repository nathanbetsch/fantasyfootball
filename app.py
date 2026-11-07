"""Fantasy football dashboard: all your Sleeper + ESPN teams on one page.

Run:  .venv\\Scripts\\python app.py   (or double-click run.bat)
"""
from __future__ import annotations

import os
import socket
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for

load_dotenv()

from ffdash import cache  # noqa: E402
from ffdash.job import load_state  # noqa: E402
from ffdash.render import fmt_pts, fmt_time  # noqa: E402
from ffdash.service import build_dashboard  # noqa: E402

app = Flask(__name__, template_folder="ffdash/templates", static_folder="ffdash/static")
app.add_template_filter(fmt_pts, "pts")
app.add_template_filter(fmt_time, "when")


@app.route("/")
def index():
    if request.args.get("refresh"):
        cache.clear()
        return redirect(url_for("index"))
    dash = build_dashboard()
    return render_template(
        "dashboard.html",
        dash=dash,
        alerts=load_state().get("log", []),
        waiver_ideas=[],
        css_href=url_for("static", filename="style.css"),
        refresh_href="?refresh=1",
        updated=datetime.now().strftime("%a %I:%M %p").replace(" 0", " "),
    )


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
    print(f"\n  Dashboard on this PC:   http://127.0.0.1:{port}")
    if host == "0.0.0.0":
        print(f"  On your phone (Wi-Fi):  http://{lan_ip()}:{port}\n")
    app.run(host=host, port=port, debug=False)
