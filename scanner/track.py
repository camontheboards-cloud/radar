"""Forward test of the radar score.

Every run appends a snapshot (time, symbol, side, score, price, today's σ) to history/YYYY-MM-DD.csv,
kept on the repo's `history` branch. From those snapshots it measures what price did next:
the move 4 hours and 24 hours later, in the trade's direction, in units of that day's forecast σ.
The site shows the result per score bucket, so you can see whether high scores actually do better.
"""
import datetime as dt
import glob
import json
import os

import pandas as pd

BUCKETS = [(0, 4, "0–4"), (5, 6, "5–6"), (7, 8, "7–8"), (9, 10, "9–10")]
HORIZONS = {"4h": pd.Timedelta(hours=4), "24h": pd.Timedelta(hours=24)}
KEEP_DAYS = 180
STATS_DAYS = 90


def record(rows, hist_dir):
    os.makedirs(hist_dir, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    snap = pd.DataFrame([{
        "run": now.isoformat(timespec="minutes"), "asof": r["asof"], "tkr": r["tkr"], "cls": r["cls"],
        "side": r["side"], "score": r["score"], "play": r["play"], "price": r["price"], "sig_pts": r.get("sig_pts"),
    } for r in rows])
    path = os.path.join(hist_dir, now.strftime("%Y-%m-%d") + ".csv")
    snap.to_csv(path, mode="a", header=not os.path.exists(path), index=False)
    # drop files past the retention window
    cutoff = (now - dt.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    for f in glob.glob(os.path.join(hist_dir, "*.csv")):
        if os.path.basename(f)[:10] < cutoff:
            os.remove(f)


def stats(hist_dir):
    files = sorted(glob.glob(os.path.join(hist_dir, "*.csv")))[-STATS_DAYS:]
    if not files:
        return None
    h = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    h["asof"] = pd.to_datetime(h["asof"], utc=True, errors="coerce")
    h = h.dropna(subset=["asof", "price"])
    # one snapshot per symbol per bar: closed markets repeat the same bar every hour, which would add fake zeros
    h = h.sort_values("run").drop_duplicates(["tkr", "asof"], keep="first").sort_values("asof")
    out = {"since": h["asof"].min().isoformat(), "snapshots": int(len(h)), "horizons": {}}
    px = h[["tkr", "asof", "price"]].rename(columns={"asof": "t2", "price": "p2"})
    for name, td in HORIZONS.items():
        base = h[(h["side"] != 0) & (h["sig_pts"] > 0)].copy()
        base["target"] = base["asof"] + td
        m = pd.merge_asof(base.sort_values("target"), px.sort_values("t2"), left_on="target", right_on="t2",
                          by="tkr", direction="forward", tolerance=pd.Timedelta(hours=3))
        m = m.dropna(subset=["p2"])
        m["r"] = m["side"] * (m["p2"] - m["price"]) / m["sig_pts"]
        res = {}
        for lo, hi, label in BUCKETS:
            g = m[(m["score"] >= lo) & (m["score"] <= hi)]["r"]
            res[label] = {"n": int(len(g)), "mean": round(float(g.mean()), 3) if len(g) else None,
                          "hit": round(float((g > 0).mean()) * 100, 1) if len(g) else None}
        g = m["r"]
        res["all"] = {"n": int(len(g)), "mean": round(float(g.mean()), 3) if len(g) else None,
                      "hit": round(float((g > 0).mean()) * 100, 1) if len(g) else None}
        out["horizons"][name] = res
    return out


def run(rows, hist_dir, out_path):
    record(rows, hist_dir)
    s = stats(hist_dir)
    with open(out_path, "w") as f:
        json.dump(s or {}, f, separators=(",", ":"))
