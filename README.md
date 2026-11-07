# fantasyfootball

A personal dashboard that puts all of my Sleeper and ESPN fantasy teams on one page.

**Four pages, styled like an iPhone app** (tab bar at the bottom)
- **News:** the top 2–3 fantasy-impact stories of the past 48 hours (with which of your
  players they affect), plus 1–2 of the biggest general NFL stories, and your recent alerts
- **One page per league:**
  1. Your matchup, record and standing
  2. Lineup fixes: empty slots, byes, injured starters, and "start X over Y" from projections
  3. Your starters and bench with projections
  4. Trade ideas to request: offers that are even on a trade calculator but improve your
     roster without hurting theirs. Dynasty (We Cummin) uses **Dynasty Daddy's trade
     calculator** with league-infused values (superflex, lineup slots, TE premium, scoring)
     and its stud-player adjustment; redraft leagues use **FantasyCalc** redraft values.
  5. Waiver targets: best available players, flagged when trending or filling a need

**Phone alerts (every 30 min, none 1–8 AM Eastern)**
- One of my players gets worse on the injury report
- An NFL starter goes Doubtful/Out/IR → the replacement on his depth chart, per league,
  marked **PICK UP** when I actually need that position (my starter hurt/on bye, superflex, etc.)
- Hot trending adds that are available to me
- News stories that tag one of my players

Alerts only fire on *changes*, so the same news never buzzes twice.

Planned: trade finder (v3).

## Runs free on GitHub (no PC needed)

`.github/workflows/update.yml` runs every 30 minutes on GitHub Actions: it pulls the
leagues + NFL injury report, news and trending adds, sends ntfy pushes, and publishes the
dashboard to GitHub Pages at https://nathanbetsch.github.io/fantasyfootball/.

One-time setup:
1. **Make the repo public** (free Pages needs it): Settings → General → Danger Zone →
   Change visibility. No secrets are in the code; `.env` is never committed.
2. **Turn on Pages:** Settings → Pages → Source: **GitHub Actions**.
3. **Add secrets:** Settings → Secrets and variables → Actions → New repository secret:
   `ESPN_S2`, `ESPN_SWID`, `NTFY_TOPIC` (copy each value from your `.env`).
4. **Phone:** install **ntfy** (App Store / Play Store), tap **+**, subscribe to the topic
   name from `NTFY_TOPIC`. Keep the default server `ntfy.sh`.
5. **First run:** Actions tab → *Update dashboard & alerts* → **Run workflow**. You should get
   a "Fantasy alerts are on" push, and the dashboard link goes live within a minute or two.

Test locally without sending anything:
```
.venv\Scripts\python -m ffdash.job --dry-run --force
```

## Run it

Double-click `run.bat`, or:

```
.venv\Scripts\python app.py
```

Then open http://127.0.0.1:5000. The console also prints a `http://192.168.x.x:5000` address
for your phone (same Wi-Fi). The first time, Windows may ask whether to allow Python through
the firewall; allow it on **Private networks** for phone access.

### First-time setup on a new machine

```
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

## Settings (`.env`)

| Setting | What it is |
|---|---|
| `SLEEPER_USERNAME` | Your Sleeper username; all your leagues for `SEASON` are loaded |
| `ESPN_LEAGUE_ID` | The `leagueId=` number in your ESPN league URL |
| `ESPN_S2`, `ESPN_SWID` | Login cookies for private ESPN leagues (below) |
| `ESPN_LEAGUE_TYPE` | `redraft`, `keeper`, or `dynasty` (just a label) |
| `HOST` | `0.0.0.0` = reachable from your phone on Wi-Fi; `127.0.0.1` = this PC only |

`.env` is in `.gitignore` and never gets committed.

### Getting the ESPN cookies (private leagues)

1. In Chrome or Edge, log in at https://fantasy.espn.com and open your league.
2. Press **F12**, go to the **Application** tab, then **Cookies** → `https://fantasy.espn.com`.
3. Copy the value of **`espn_s2`** (long string) into `ESPN_S2=`.
4. Copy the value of **`SWID`** (looks like `{ABCD-1234-...}`, keep the braces) into `ESPN_SWID=`.
5. Save `.env` and restart the app.

These cookies work like a password for your ESPN account, so keep them private. They last
about a year; if ESPN shows an error on the dashboard, copy fresh ones.

## Data sources

- Sleeper public API (no login): https://docs.sleeper.com
- ESPN fantasy API (unofficial) at `lm-api-reads.fantasy.espn.com`
- Bye weeks: ESPN's public pro-team schedule
