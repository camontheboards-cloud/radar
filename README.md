# Core Stack Radar

A Maverick-style multi-timeframe scanner built on your core stack:
Kernel Momentum · VR Regime · Norm Flow · BBWP (15m / 1H / 4H / 1D), plus Volatility Forecast (σ today,
day position), Liquidity (PDH / PDL / PWH / PWL, sweeps), the playbook column and a 0–10 alignment score.

It covers 127 symbols: prop-firm futures (CME / COMEX / NYMEX / CBOT), the top 20 crypto, 16 forex pairs,
40 large-cap stocks, 12 ETFs and 8 indices. Edit `scanner/universe.py` to change the list.

## How it works

GitHub Actions runs `scanner/scan.py` every hour at :05. It downloads prices from Yahoo Finance, runs the
indicator math (`scanner/indicators.py`, ported from the Pine scripts) and publishes `site/` to GitHub Pages.
Free, nothing to keep running on your computer.

## Setup (about 5 minutes)

1. Create a free GitHub account if you don't have one, then **New repository** → name it `radar` →
   **Public** (free GitHub Pages needs a public repo) → Create.
2. On the new repo page click **uploading an existing file**, drag in everything from this folder
   (including the `.github` folder) and **Commit changes**.
3. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
4. **Actions** tab → enable workflows if asked → **Radar scan → Run workflow**. The first run takes a few minutes.
5. Your site: `https://<your-username>.github.io/radar/`

## Notes

- **Flow is a proxy.** Yahoo has no bid/ask volume, so delta is estimated from where each bar closes in its
  range. Your TradingView Norm Flow uses real footprint delta; trust that one for entries.
- **Futures** use Yahoo's continuous front-month (NQ=F stands in for both NQ and MNQ).
- **Delays:** some exchanges are 10–15 minutes delayed on Yahoo, and GitHub can start scheduled runs late.
  The radar is for picking what to open on TradingView, not for timing entries.
- **Yahoo limits:** if a run gets rate-limited, the missing symbols are listed at the bottom of the page and
  come back on the next run.
- **60-day rule:** GitHub pauses scheduled workflows in a repo with no commits for 60 days. If the page stops
  updating, re-enable it in the Actions tab (or make any small commit).
- Test locally without internet: `python scanner/scan.py --demo`, then `python -m http.server -d site`.
