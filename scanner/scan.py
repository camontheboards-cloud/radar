"""Radar scanner: downloads OHLCV for the universe, runs the indicators on 15m / 1H / 4H / 1D and
writes site/data.json for the web page.

    python scanner/scan.py            # live data from Yahoo Finance
    python scanner/scan.py --demo     # synthetic random data, to test the page without a network
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from indicators import bbwp, kernel_momentum, liquidity, norm_flow, vol_forecast, vr_regime  # noqa: E402
from universe import UNIVERSE  # noqa: E402

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(__file__), "..", "site", "data.json")
TFS = ("15m", "1h", "4h", "1d")


# ─── data ─────────────────────────────────────────────────────────────────
def _clean(df):
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    df = df[(df["high"] > 0) & (df["low"] > 0)]
    return df[~df.index.duplicated(keep="last")].sort_index()


def _download(tickers, interval, period, tries=3):
    import yfinance as yf
    out = {}
    for i in range(0, len(tickers), 40):
        batch = tickers[i:i + 40]
        for attempt in range(tries):
            try:
                raw = yf.download(batch, interval=interval, period=period, group_by="ticker",
                                  threads=True, progress=False, auto_adjust=True)
                break
            except Exception as e:  # rate limit or network blip: back off and retry
                print(f"  {interval} batch {i}: {e}; retry {attempt + 1}", file=sys.stderr)
                time.sleep(10 * (attempt + 1))
        else:
            continue
        for t in batch:
            try:
                df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                df = _clean(df)
                if len(df) > 50:
                    out[t] = df
            except Exception:
                pass
    return out


def _to_4h(h1):
    # 4H bars anchored to the 18:00 New York futures session open (18, 22, 02, 06, 10, 14)
    x = h1.copy()
    x.index = (x.index.tz_convert("America/New_York") if x.index.tz is not None
               else x.index.tz_localize("UTC").tz_convert("America/New_York"))
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return x.resample("4h", offset="2h").agg(agg).dropna(subset=["close"])


def load_live():
    tickers = list(UNIVERSE)
    print("downloading 15m…"); m15 = _download(tickers, "15m", "60d")
    print("downloading 1h…");  h1 = _download(tickers, "60m", "730d")
    print("downloading 1d…");  d1 = _download(tickers, "1d", "5y")
    data = {}
    for t in tickers:
        if t in d1:
            data[t] = {"15m": m15.get(t), "1h": h1.get(t), "4h": _to_4h(h1[t]) if t in h1 else None, "1d": d1[t]}
    return data


def load_demo(seed=7):
    """Random-walk prices with changing trend / chop regimes, so every column has something to show."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.utcnow().floor("15min"), periods=4 * 24 * 365 * 2, freq="15min", tz="UTC")
    data = {}
    for t, (name, cls) in UNIVERSE.items():
        n = len(idx)
        vol = rng.uniform(0.0008, 0.004)
        drift = np.repeat(rng.normal(0, vol * 0.15, n // 2000 + 1), 2000)[:n]
        ar = np.repeat(rng.uniform(-0.3, 0.3, n // 3000 + 1), 3000)[:n]
        e = rng.normal(0, vol, n)
        r = np.empty(n); r[0] = e[0]
        for i in range(1, n):
            r[i] = drift[i] + ar[i] * r[i - 1] + e[i]
        close = rng.uniform(1, 500) * np.exp(np.cumsum(r))
        spread = np.abs(rng.normal(0, vol, n)) * close
        openp = np.r_[close[0], close[:-1]]
        high = np.maximum(openp, close) + spread
        low = np.minimum(openp, close) - spread
        volume = 0 if cls in ("forex", "indices") else rng.lognormal(8, 0.6, n) * (1 + 50 * np.abs(r))
        df = pd.DataFrame({"open": openp, "high": high, "low": low, "close": close, "volume": volume}, index=idx)
        agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        h1 = df.resample("1h").agg(agg)
        data[t] = {"15m": df.iloc[-60 * 96:], "1h": h1, "4h": _to_4h(h1),
                   "1d": df.resample("1D").agg(agg)}
    return data


# ─── per-symbol scan ──────────────────────────────────────────────────────
def playbook(km1h, vr15):
    """The playbook's VR × Kernel Momentum table (side from 1H KM, regime from 15m VR)."""
    if km1h is None or vr15 is None:
        return None
    side, reg = km1h["st"], vr15["st"]
    if side != 0:
        return "A · trend" if reg == 1 else "A · pullback"
    return "C · break-retest" if reg == 1 else "B · range fade" if reg == -1 else "wait"


def score(row):
    """0–10: how many things agree with the 1H Kernel Momentum side."""
    d = row["side"]
    if d == 0:
        return 0
    pts, mx = 0.0, 0.0
    for tf in TFS:
        km = row["tf"][tf]["km"]
        mx += 1.5
        if km and km["st"] == d:
            pts += 1.5
    for tf in ("15m", "1h"):
        fl = row["tf"][tf]["flow"]
        if fl is not None:
            mx += 1
            if fl["v"] * d >= 0.5:
                pts += 1
    vr = row["tf"]["15m"]["vr"]
    mx += 1
    if vr and vr["st"] == 1:
        pts += 1
    pos = row["vol"]["pos"] if row["vol"] else None
    mx += 1
    if pos is not None and pos * d < 2:
        pts += 1
    return int(round(10 * pts / mx)) if mx else 0


def scan_symbol(t, frames):
    name, cls = UNIVERSE[t]
    d1 = frames["1d"]
    row = {"sym": name, "tkr": t, "cls": cls, "tf": {}}
    for tf in TFS:
        df = frames.get(tf)
        if df is None or len(df) < 300:
            row["tf"][tf] = {"km": None, "vr": None, "flow": None, "bbwp": None}
            continue
        row["tf"][tf] = {"km": kernel_momentum(df), "vr": vr_regime(df), "flow": norm_flow(df), "bbwp": bbwp(df)}
    # price from the freshest frame
    fresh = next((frames[tf] for tf in ("15m", "1h", "1d") if frames.get(tf) is not None), d1)
    last = float(fresh["close"].iloc[-1])
    row["price"] = last
    row["chg"] = round(100 * (last / float(d1["close"].iloc[-2]) - 1), 2) if len(d1) > 2 else None
    row["asof"] = fresh.index[-1].isoformat()
    vf = vol_forecast(d1)
    row["vol"] = {k: vf[k] for k in ("sig_pct", "rising", "pos")} if vf else None
    row["liq"] = liquidity(d1, vf["sig_pts"]) if vf else None
    km1h = row["tf"]["1h"]["km"]
    row["side"] = km1h["st"] if km1h else 0
    row["fresh"] = bool(km1h and km1h["fresh"])
    row["play"] = playbook(km1h, row["tf"]["15m"]["vr"])
    row["score"] = score(row)
    return row


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if (math.isnan(o) or math.isinf(o)) else round(float(o), 6)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    data = load_demo() if args.demo else load_live()
    rows, failed = [], []
    for t, frames in data.items():
        try:
            rows.append(scan_symbol(t, frames))
        except Exception as e:
            failed.append(t)
            print(f"  {t}: {e}", file=sys.stderr)
    missing = [t for t in UNIVERSE if t not in data]
    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "demo": args.demo,
        "count": len(rows),
        "missing": missing + failed,
        "rows": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(_jsonable(out), f, separators=(",", ":"), ensure_ascii=False)
    print(f"{len(rows)} symbols in {time.time() - t0:.0f}s · missing {len(out['missing'])}: {out['missing'][:12]}")


if __name__ == "__main__":
    main()
