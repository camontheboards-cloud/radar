"""Indicator math for the radar. Each function mirrors the Pine script it is named after.

All inputs are pandas DataFrames with columns open/high/low/close/volume and a DatetimeIndex.
Rolling standard deviations use ddof=0, like Pine's ta.stdev / ta.variance.
"""
import numpy as np
import pandas as pd
from scipy.signal import lfilter


# ─── helpers ──────────────────────────────────────────────────────────────
def _std(s, n):
    return s.rolling(n, min_periods=n).std(ddof=0)


def _rma(s, n):  # Wilder's moving average (Pine ta.rma / ta.atr)
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n):
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return _rma(tr, n)


def supersmoother(s, period):
    """Ehlers SuperSmoother, same coefficients as f_ss() in kernel-momentum.txt."""
    a1 = np.exp(-1.414 * np.pi / period)
    b1 = 2 * a1 * np.cos(1.414 * np.pi / period)
    c3 = -a1 * a1
    c1 = 1 - b1 - c3
    x = s.to_numpy(dtype=float)
    y = lfilter([c1 / 2, c1 / 2], [1.0, -b1, -c3], x, zi=lfilter_zi_like(x[0], c1, b1, c3))[0]
    return pd.Series(y, index=s.index)


def lfilter_zi_like(x0, c1, b1, c3):
    # start the filter at the first price (Pine starts with f = s), so there is no warm-up dip from zero
    from scipy.signal import lfilter_zi
    return lfilter_zi([c1 / 2, c1 / 2], [1.0, -b1, -c3]) * x0


# ─── Kernel Momentum (Baz et al. normalized MACD, SuperSmoother mode) ──────
KM_SPEEDS = ((4, 12), (8, 24), (16, 48))


def kernel_momentum(df, atr_len=63, z_len=252, band=0.3):
    """Returns dict(score, up, n, state, fresh). score in σ; state +1 LONG / −1 SHORT / 0 FLAT."""
    c = df["close"]
    vol = atr(df, atr_len)
    zs = []
    for hf, hs in KM_SPEEDS:
        raw = (supersmoother(c, 3.5 * hf) - supersmoother(c, 3.5 * hs)) / vol
        sd = _std(raw, z_len)
        zs.append(raw / sd.replace(0, np.nan))
    avg = sum(zs) / 3
    sc = avg / _std(avg, z_len).replace(0, np.nan)
    sc = sc.dropna()
    if len(sc) < 5:
        return None
    last = float(sc.iloc[-1])
    state = 1 if last >= band else -1 if last <= -band else 0
    st = np.where(sc >= band, 1, np.where(sc <= -band, -1, 0))
    # fresh = the state changed within the last 3 bars
    fresh = bool(state != 0 and (st[-4:-1] != state).any())
    up = int(sum(1 for z in zs if z.iloc[-1] > 0))
    return {"v": round(last, 2), "st": state, "up": up, "fresh": fresh}


# ─── Variance Ratio regime (Lo & MacKinlay; the VR Regime script) ──────────
def vr_regime(df, k=8, n=120, smooth=3, z_thr=1.96):
    c = np.log(df["close"])
    r1 = c.diff()
    rk = c.diff(k)
    v1 = r1.rolling(n, min_periods=n).var(ddof=0)
    vk = rk.rolling(n, min_periods=n).var(ddof=0)
    vr = (vk / (k * v1)).rolling(smooth).mean().dropna()
    if vr.empty:
        return None
    v = float(vr.iloc[-1])
    phi = 2.0 * (2 * k - 1) * (k - 1) / (3.0 * k * n)
    z = (v - 1) / np.sqrt(phi)
    reg = 1 if z > z_thr else -1 if z < -z_thr else 0
    return {"v": round(v, 2), "z": round(float(z), 2), "st": reg}


# ─── Normalized Order Flow (volume-delta proxy) ──────────────────────────
def norm_flow(df, speeds=(5, 15, 45), z_len=252):
    """Delta is estimated from where each bar closes in its range (close-location value × volume),
    because free data has no real bid/ask volume. Same normalization as normalized-order-flow.txt."""
    v = df["volume"].fillna(0)
    if v.tail(z_len).sum() <= 0 or (v.tail(z_len) > 0).mean() < 0.5:
        return None  # no usable volume (forex, most indices)
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    clv = ((2 * df["close"] - df["high"] - df["low"]) / rng).fillna(0)
    d = clv * v
    zs = []
    for n in speeds:
        imb = _ema(d, n) / _ema(v, n).replace(0, np.nan)
        zs.append(imb / _std(imb, z_len).replace(0, np.nan))
    avg = (zs[0] + zs[1] + zs[2]) / 3
    fl = (avg / _std(avg, z_len).replace(0, np.nan)).dropna()
    if fl.empty:
        return None
    last = float(fl.iloc[-1])
    up = sum(1 for z in zs if z.iloc[-1] > 0)
    agree = up if last >= 0 else 3 - up
    return {"v": round(last, 2), "agree": int(agree)}


# ─── BBWP (The_Caretaker's percentile rank; BBWP-styled.txt defaults) ──────
def bbwp(df, basis_len=7, lookback=100):
    c = df["close"]
    bbw = (2 * _std(c, basis_len) / c.rolling(basis_len).mean()).dropna()
    if len(bbw) < 20:
        return None
    hist = bbw.iloc[-lookback - 1:-1].to_numpy()  # the previous `lookback` values, current excluded
    cur = bbw.iloc[-1]
    pct = 100.0 * (hist <= cur).sum() / len(hist)
    prev_hist = bbw.iloc[-lookback - 2:-2].to_numpy()
    prev = 100.0 * (prev_hist <= bbw.iloc[-2]).sum() / max(len(prev_hist), 1)
    return {"v": round(float(pct), 1), "d": round(float(pct - prev), 1)}


# ─── Volatility Forecast (HAR-RV + EWMA, vol-forecast.txt) ───────────────
def vol_forecast(daily, fit_n=500, lam=0.94):
    """Forecast of TODAY's σ (log units), made at yesterday's close. Returns None if < 60 usable days."""
    d = daily.dropna(subset=["open", "high", "low", "close"])
    if len(d) < 90:
        return None
    o, h, l, c = (d[k].astype(float) for k in ("open", "high", "low", "close"))
    gk = 0.5 * np.log(h / l) ** 2 - (2 * np.log(2) - 1) * np.log(c / o) ** 2
    gap = (np.log(o / c.shift(1)) ** 2).fillna(0)
    rv = gk.clip(lower=0) + gap
    rvw = rv.rolling(5).mean()
    rvm = rv.rolling(22).mean()
    # model state at yesterday's close (everything up to the previous bar), forecasting today
    rv_, rvw_, rvm_ = rv.iloc[:-1], rvw.iloc[:-1], rvm.iloc[:-1]
    X = pd.concat([pd.Series(1.0, index=rv_.index), rv_.shift(1), rvw_.shift(1), rvm_.shift(1)], axis=1).dropna()
    y = rv_.loc[X.index]
    X, y = X.tail(fit_n) * [1, 1e4, 1e4, 1e4], y.tail(fit_n) * 1e4
    har = None
    if len(X) >= 60:
        beta = np.linalg.pinv(X.to_numpy()) @ y.to_numpy()
        xn = np.array([1.0, rv_.iloc[-1] * 1e4, rvw_.iloc[-1] * 1e4, rvm_.iloc[-1] * 1e4])
        har = max(float(xn @ beta) / 1e4, 0.25 * float(rvm_.iloc[-1]))
    ew = rv_.ewm(alpha=1 - lam, adjust=False).mean().iloc[-1]
    var = har if har is not None else float(ew)
    sig = float(np.sqrt(var))
    prev_close = float(c.iloc[-2])
    day_open = float(o.iloc[-1])
    last = float(c.iloc[-1])
    pos = (last - day_open) / (sig * prev_close) if sig > 0 else None
    return {
        "sig_pct": round(sig * 100, 2),            # today's expected 1σ move, %
        "sig_pts": sig * prev_close,               # in price units
        "rising": bool(har is not None and har > float(ew) * 1.15),
        "pos": round(pos, 2) if pos is not None else None,  # price vs today's open, in σ
        "open": day_open,
    }


# ─── Liquidity (previous day / week highs and lows, sweeps) ───────────────
def overnight_range(m15):
    """Futures overnight (Globex) high / low: 18:00 → 09:30 New York of the current session.
    Returned only once the cash session has opened; before that the overnight range is still forming."""
    if m15 is None or len(m15) < 10:
        return None, None
    x = m15.copy()
    x.index = x.index.tz_convert("America/New_York") if x.index.tz is not None else x.index.tz_localize("UTC").tz_convert("America/New_York")
    now = x.index[-1]
    if not (now.hour > 9 or (now.hour == 9 and now.minute >= 30)) or now.hour >= 17:
        return None, None
    start = (now - pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=18)
    if now.weekday() == 0:  # Monday: the session opened Sunday 18:00
        start -= pd.Timedelta(days=1)
    end = now.normalize() + pd.Timedelta(hours=9, minutes=30)
    on = x[(x.index >= start) & (x.index < end)]
    if len(on) < 4:
        return None, None
    return float(on["high"].max()), float(on["low"].min())


def liquidity(daily, sig_pts, m15=None, futures=False):
    d = daily.dropna(subset=["high", "low", "close"])
    if len(d) < 10 or not sig_pts:
        return None
    today = d.iloc[-1]
    pdh, pdl = float(d["high"].iloc[-2]), float(d["low"].iloc[-2])
    wk = d.iloc[:-1].resample("W-FRI").agg({"high": "max", "low": "min"}).dropna()
    # previous COMPLETE week (the last group may be the current, unfinished week)
    cur_week = d.index[-1].to_period("W-FRI")
    wk = wk[wk.index.to_period("W-FRI") < cur_week]
    pwh, pwl = (float(wk["high"].iloc[-1]), float(wk["low"].iloc[-1])) if len(wk) else (None, None)
    last, hi, lo = float(today["close"]), float(today["high"]), float(today["low"])
    levels = {"PDH": pdh, "PDL": pdl, "PWH": pwh, "PWL": pwl}
    rth_hi = rth_lo = None
    if futures:
        onh, onl = overnight_range(m15)
        if onh is not None:
            levels.update({"ONH": onh, "ONL": onl})
            # today's high / low so far must only count the cash session for the ON levels
            x = m15.copy()
            x.index = x.index.tz_convert("America/New_York")
            rth = x[x.index >= x.index[-1].normalize() + pd.Timedelta(hours=9, minutes=30)]
            rth_hi, rth_lo = float(rth["high"].max()), float(rth["low"].min())
    def hl(name):
        return (rth_hi, rth_lo) if name.startswith("ON") else (hi, lo)

    sweeps = []
    for name, px in levels.items():
        if px is None:
            continue
        h_, l_ = hl(name)
        if name.endswith("H") and h_ > px and last < px:
            sweeps.append(name + " swept ↩")
        if name.endswith("L") and l_ < px and last > px:
            sweeps.append(name + " swept ↩")
    # nearest level price has NOT traded through today
    best = None
    for name, px in levels.items():
        if px is None:
            continue
        h_, l_ = hl(name)
        taken = (name.endswith("H") and h_ >= px) or (name.endswith("L") and l_ <= px)
        if taken:
            continue
        dist = (px - last) / sig_pts
        if best is None or abs(dist) < abs(best[1]):
            best = (name, dist)
    return {
        "near": best[0] if best else None,
        "dist": round(best[1], 2) if best else None,   # signed, in daily σ (+ = above price)
        "sweep": sweeps[0] if sweeps else None,
    }
