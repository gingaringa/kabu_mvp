import pandas as pd
import numpy as np

def screen_by_liquidity(daily_df: pd.DataFrame, date, min_adv=1e8, top_n=10):
    day = daily_df[daily_df["date"]==date].copy()
    if day.empty:
        day = daily_df.sort_values("date").groupby("code").tail(1).copy()
    day["adv"] = day["Close"] * day["Volume"]
    cand = day.sort_values("adv", ascending=False)
    cand = cand[cand["adv"]>=min_adv]
    return cand.head(top_n)["code"].tolist()

def compute_screen_metrics(daily_df: pd.DataFrame, date, atr_window: int = 20) -> pd.DataFrame:
    """
    指定日の各コードについて ADV / ATR% / ギャップ% を計算して返す
    戻り値: columns=[code, date, Open, Close, Volume, adv, atr_pct, gap_pct]
    """
    d = daily_df.sort_values(["code","date"]).copy()
    d["prev_close"] = d.groupby("code")["Close"].shift(1)

    prev_close = d["prev_close"].fillna(d["Close"])
    tr = pd.concat([
        (d["High"] - d["Low"]).abs(),
        (d["High"] - prev_close).abs(),
        (d["Low"]  - prev_close).abs()
    ], axis=1).max(axis=1)
    d["TR"] = tr
    d["ATR"] = d.groupby("code")["TR"].transform(lambda s: s.rolling(atr_window, min_periods=1).mean())
    d["ATR_prev"] = d.groupby("code")["ATR"].shift(1)

    day = d[d["date"]==date].copy()
    if day.empty:
        day = d.groupby("code").tail(1).copy()

    day["adv"] = day["Close"] * day["Volume"]
    day["gap_pct"] = 100.0 * (day["Open"] - day["prev_close"]) / day["prev_close"]
    day["atr_pct"] = 100.0 * (day["ATR_prev"] / day["prev_close"])
    return day[["code","date","Open","Close","Volume","adv","atr_pct","gap_pct"]].sort_values("adv", ascending=False)