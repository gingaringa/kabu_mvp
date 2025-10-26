import pandas as pd
import numpy as np

def vwap(df: pd.DataFrame):
    pv = (df["Close"] * df["Volume"]).cumsum()
    vv = df["Volume"].cumsum().replace(0, np.nan)
    return pv / vv

def compute_orb_signals(
    min1: pd.DataFrame,
    or_minutes: int = 5,
    use_vwap: bool = True,
    entry_not_before: int = 3,          # 例: 9:03以降
    spread_limit: float = 0.0005,       # 0.05%
    require_book: bool = False,         # 板厚チェックを有効化する場合 True
    min_bid_qty: int = 0,
    min_ask_qty: int = 0,
    tp_rr: float = 1.0,                 # RR=1で半利確
    trail_on_vwap: bool = True,         # 半利確後はVWAP割れで残りクローズ
    tick_size: float = 1.0,             # 呼び値
    min_stop_ticks: int = 0             # 最小ストップ幅（ティック）
):
    """
    ORB(最初or_minutes分の高安) + 任意フィルタ + TP/トレーリングの簡易実装
    DataFrame列（任意拡張）: Open, High, Low, Close, Volume, [Bid, Ask, BidSize, AskSize]
    返却: dict(entry/exit/tp/stop/or_high/or_low)
    """
    df = min1.copy()
    df["VWAP"] = vwap(df)

    # ORレンジ
    or_window = df.iloc[:or_minutes]
    or_high = float(or_window["High"].max())
    or_low  = float(or_window["Low"].min())

    # 板チェック関数
    def book_ok(i: int) -> bool:
        if {"Bid","Ask"}.issubset(df.columns):
            bid = float(df["Bid"].iloc[i])
            ask = float(df["Ask"].iloc[i])
            if bid <= 0 or ask <= 0:  # 不正値
                return False
            mid = (bid + ask) / 2.0
            spr = (ask - bid) / mid
            if spr > spread_limit:
                return False
            if require_book:
                if "BidSize" in df.columns and "AskSize" in df.columns:
                    if (int(df["BidSize"].iloc[i]) < min_bid_qty) or (int(df["AskSize"].iloc[i]) < min_ask_qty):
                        return False
        # 板情報がなければ通す（モック時）
        return True

    # エントリ探索（OR完了＋entry_not_before以降）
    start_idx = max(or_minutes, entry_not_before)
    entry_idx = None
    for i in range(start_idx, len(df)):
        price = float(df["Close"].iloc[i])
        if price > or_high:
            if (not use_vwap) or (price >= float(df["VWAP"].iloc[i])):
                if book_ok(i):
                    entry_idx = i
                    break

    signal = {"entry": None, "exit": None, "tp": None,
              "stop": None, "or_high": or_high, "or_low": or_low}
    if entry_idx is None:
        return signal

    entry_price = float(df["Close"].iloc[entry_idx])
    # 推奨ストップ：OR安値と最小ティック幅の上位を採用
    min_stop = entry_price - tick_size * max(min_stop_ticks, 0)
    stop_price = float(max(or_low, min_stop))
    signal["stop"] = stop_price

    # 目標利確価格（RR=tp_rr）
    tp_price = entry_price + tp_rr * (entry_price - stop_price)
    tp_hit = False
    tp_idx = None

    # 退出ロジック
    exit_idx = None
    exit_reason = "eod"

    for j in range(entry_idx + 1, len(df)):
        lo = float(df["Low"].iloc[j])
        hi = float(df["High"].iloc[j])
        cl = float(df["Close"].iloc[j])
        vwap_now = float(df["VWAP"].iloc[j])

        # ストップ
        if lo <= stop_price:
            exit_idx = j
            exit_reason = "stop"
            break

        # まだ半利確していなければRR到達で半利確
        if (not tp_hit) and (hi >= tp_price):
            tp_hit = True
            tp_idx = j
            signal["tp"] = {"t": df.index[j], "price": float(df["Close"].iloc[j])}

        # 半利確後はVWAP割れで残りクローズ（任意）
        if tp_hit and trail_on_vwap and (cl < vwap_now):
            exit_idx = j
            exit_reason = "tp_trail"
            break

    if exit_idx is None:
        exit_idx = len(df) - 1  # 引け
        exit_reason = "eod" if not tp_hit else "tp_eod"

    signal["entry"] = {"t": df.index[entry_idx], "price": entry_price}
    signal["exit"]  = {"t": df.index[exit_idx],  "price": float(df["Close"].iloc[exit_idx]),
                       "reason": exit_reason}
    return signal

def size_by_risk(entry_price, stop_price, capital, risk_pct, lot_size=100, tick_size=1.0):
    # リスクベース
    risk_per_share = max(entry_price - stop_price, tick_size)
    risk_budget = capital * risk_pct
    shares_by_risk = int((risk_budget // risk_per_share) // lot_size * lot_size)
    # 現金上限（資金100%）
    max_cost_pct = 1.0
    cost_cap = capital * max_cost_pct
    shares_by_cash = int((cost_cap // entry_price) // lot_size * lot_size)
    shares = min(shares_by_risk, shares_by_cash)
    return max(shares, 0)