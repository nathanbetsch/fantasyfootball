# fantasyfootball

A personal dashboard that puts all of my Sleeper and ESPN fantasy teams on one page.

**Version 1 (current):**
- Every league's roster, record, standing and this week's live matchup score
- Lineup warnings: empty slots, starters on BYE, starters who are Out/IR/Doubtful (red), or Questionable (yellow)
- Players I own in more than one league (injury exposure)
- Mobile-friendly, so it can be opened from a phone on the same Wi-Fi

Planned: waiver pickup suggestions + phone alerts (v2), trade finder (v3).

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
