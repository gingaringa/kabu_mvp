import datetime as dt
import math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # .../kabu_mvp
CACHE = ROOT / "cache"
CACHE.mkdir(exist_ok=True)

# 取引時間（東証現物）
AM_START = dt.time(9, 0); AM_END = dt.time(11, 30)
PM_START = dt.time(12, 30); PM_END = dt.time(15, 0)

def _minutes_session(date: dt.date):
    def rng(s, e):
        t = pd.date_range(dt.datetime.combine(date, s), dt.datetime.combine(date, e), freq="1min", inclusive="left")
        return t
    return pd.Index(rng(AM_START, AM_END).append(rng(PM_START, PM_END)))

def _bridge_sim(row, date: dt.date) -> pd.DataFrame:
    o, h, l, c, v = [float(row[k]) for k in ["Open","High","Low","Close","Volume"]]
    idx = _minutes_session(date)
    n = len(idx)
    span = max(h - l, 1e-6)
    base = np.linspace(o, c, n)
    noise = np.cumsum(np.random.default_rng(int(date.strftime("%Y%m%d"))).normal(scale=span/80, size=n))
    px = base + noise
    px = np.clip(px, min(o,l), max(c,h))
    df = pd.DataFrame(index=idx)
    df["Close"] = px
    df["Open"]  = np.r_[px[0], px[:-1]]
    df["High"]  = np.maximum(df["Open"], df["Close"]) + span/200
    df["Low"]   = np.minimum(df["Open"], df["Close"]) - span/200
    w = np.concatenate([np.linspace(0.5, 1.0, n//2), np.linspace(1.0, 0.6, n - n//2)])
    vol = (w / w.sum()) * max(v, 1e5)
    df["Volume"] = vol.astype(int)
    return df[["Open","High","Low","Close","Volume"]]

def load_daily_seed(seed_csv: Path, lookback=60) -> pd.DataFrame:
    # BOMがあっても読めるよう utf-8-sig
    tickers = pd.read_csv(seed_csv, encoding="utf-8-sig")["code"].astype(str).tolist()
    today = dt.date.today()
    rows = []
    rng = pd.date_range(end=today, periods=lookback, freq="B")
    for code in tickers:
        price = 1000 + hash(code) % 3000
        for d in rng:
            p = price * (1 + 0.001 * math.sin(d.dayofyear/3))
            o = p * (1 + np.random.randn()*0.002)
            c = p * (1 + np.random.randn()*0.002)
            hi = max(o,c) * (1 + abs(np.random.randn())*0.004)
            lo = min(o,c) * (1 - abs(np.random.randn())*0.004)
            vol = 1e6 + abs(np.random.randn())*2e5
            rows.append([code, d.date(), o, hi, lo, c, vol])
    d = pd.DataFrame(rows, columns=["code","date","Open","High","Low","Close","Volume"])
    return d

def simulate_minutes_for_date(daily_df: pd.DataFrame, date: dt.date) -> dict:
    out = {}
    for code, g in daily_df.groupby("code"):
        row = g[g["date"]==date]
        if row.empty:
            row = g.sort_values("date").iloc[-1]
        else:
            row = row.iloc[0]
        out[code] = _bridge_sim(row, date)
    return out