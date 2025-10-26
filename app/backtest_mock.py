import argparse, json, datetime as dt
from pathlib import Path
import pandas as pd

from src.data.marketdata_mock import load_daily_seed, simulate_minutes_for_date
from src.logic.screener import compute_screen_metrics
from src.logic.signals import compute_orb_signals, size_by_risk

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
LOGDIR = ROOT / "logs"

def business_days(end: dt.date, days: int):
    rng = pd.bdate_range(end=end, periods=days, freq="C")
    return [d.date() for d in rng]

def iter_days(start: dt.date, end: dt.date):
    for d in pd.bdate_range(start=start, end=end, freq="C"):
        yield d.date()

def main():
    ap = argparse.ArgumentParser()
    # 期間指定
    ap.add_argument("--start", type=str, default=None, help="YYYY-MM-DD")
    ap.add_argument("--end", type=str, default=None, help="YYYY-MM-DD（省略時=直近日の平日）")
    ap.add_argument("--days", type=int, default=None, help="直近営業日N日分（--start/--endと排他）")

    # 1日あたりの最大候補
    ap.add_argument("--max-per-day", type=int, default=None)

    # スクリーナ条件
    ap.add_argument("--min-adv", type=float, default=1e8)
    ap.add_argument("--min-atr-pct", type=float, default=None)
    ap.add_argument("--max-atr-pct", type=float, default=None)
    ap.add_argument("--gap-min", type=float, default=None)
    ap.add_argument("--gap-max", type=float, default=None)

    # シグナル条件
    ap.add_argument("--or-minutes", type=int, default=5)
    ap.add_argument("--entry-not-before", type=int, default=3)
    ap.add_argument("--spread-limit", type=float, default=0.0005)
    ap.add_argument("--tp-rr", type=float, default=1.0)
    ap.add_argument("--min-stop-ticks", type=int, default=0)

    args = ap.parse_args()

    # 期間解釈
    if args.days is not None and (args.start or args.end):
        raise SystemExit("--days と --start/--end は同時指定不可")

    today = dt.date.today()
    if args.end:
        end_day = dt.date.fromisoformat(args.end)
    else:
        d = today
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
        end_day = d

    if args.days:
        days = business_days(end_day, args.days)
    else:
        if args.start:
            start_day = dt.date.fromisoformat(args.start)
            days = list(iter_days(start_day, end_day))
        else:
            days = business_days(end_day, 20)  # 既定=直近20営業日

    if not days:
        print("No business days in range.")
        return

    # データロード（ATR計算用に長め）
    daily = load_daily_seed(CONFIG / "watchlist_seed.csv", lookback=200)

    # リスク設定（BOM安全）
    risk = json.loads((CONFIG / "risk.json").read_text("utf-8-sig"))
    tick = float(risk.get("tick_size", 1.0))
    max_per_day = args.max_per_day if args.max_per_day is not None else risk.get("max_positions", 3)

    all_trades = []

    for day in days:
        metrics = compute_screen_metrics(daily, day, atr_window=20)

        # フィルタ
        q = metrics[metrics["adv"] >= args.min_adv].copy()
        if args.min_atr_pct is not None:
            q = q[q["atr_pct"] >= args.min_atr_pct]
        if args.max_atr_pct is not None:
            q = q[q["atr_pct"] <= args.max_atr_pct]
        if args.gap_min is not None:
            q = q[q["gap_pct"] >= args.gap_min]
        if args.gap_max is not None:
            q = q[q["gap_pct"] <= args.gap_max]

        codes = q.sort_values("adv", ascending=False).head(max_per_day)["code"].astype(str).tolist()
        if not codes:
            continue

        minutes_map = simulate_minutes_for_date(daily, day)

        for code in codes:
            df = minutes_map[code]
            sig = compute_orb_signals(
                df,
                or_minutes=args.or_minutes, use_vwap=True,
                entry_not_before=args.entry_not_before,
                spread_limit=args.spread_limit,
                tp_rr=args.tp_rr,
                tick_size=tick,
                min_stop_ticks=args.min_stop_ticks
            )
            if sig["entry"] is None:
                continue

            entry = float(sig["entry"]["price"])
            stop  = float(sig.get("stop", sig["or_low"]))
            exit_price = float(sig["exit"]["price"])

            qty = size_by_risk(entry, stop, risk["capital"], risk["risk_pct"],
                               risk["lot_size"], tick)
            if qty <= 0:
                continue

            # PnL（半利確があれば 1/2 をTP価格、残りは最終Exit）
            if sig.get("tp") is not None:
                tp_price = float(sig["tp"]["price"])
                pnl = (tp_price - entry) * (qty/2) + (exit_price - entry) * (qty/2)
            else:
                pnl = (exit_price - entry) * qty

            risk_per_share = max(entry - stop, tick)
            R = pnl / (risk_per_share * qty) if risk_per_share > 0 and qty > 0 else 0.0

            all_trades.append({
                "date": day.isoformat(), "code": code,
                "entry_time": sig["entry"]["t"], "entry": entry, "stop": stop,
                "tp_time": None if sig.get("tp") is None else sig["tp"]["t"],
                "tp_price": None if sig.get("tp") is None else float(sig["tp"]["price"]),
                "exit_time": sig["exit"]["t"], "exit": exit_price,
                "exit_reason": sig["exit"]["reason"],
                "qty": qty, "pnl": pnl, "R": R
            })

    # 出力
    LOGDIR.mkdir(exist_ok=True)
    start_lbl = days[0].isoformat()
    end_lbl = days[-1].isoformat()

    out_trades = pd.DataFrame(all_trades)
    out_path = LOGDIR / f"bt_trades_{start_lbl}_to_{end_lbl}.csv"
    out_trades.to_csv(out_path, index=False, encoding="utf-8-sig")

    # サマリ
    if out_trades.empty:
        print("No trades in backtest.")
        print(f"[saved] {out_path}")
        return

    wins = int((out_trades["pnl"] > 0).sum())
    total = int(len(out_trades))
    win_rate = 100.0 * wins / total
    expectancy = float(out_trades["pnl"].mean())
    avg_R = float(out_trades["R"].mean())
    cum_pnl = float(out_trades["pnl"].sum())

    print("=== BACKTEST SUMMARY ===")
    print(f"Period        : {start_lbl} -> {end_lbl} ({total} trades)")
    print(f"Win rate      : {win_rate:.1f}%")
    print(f"Avg PnL/trade : {expectancy:.1f}")
    print(f"Avg R         : {avg_R:.2f}")
    print(f"Total PnL     : {cum_pnl:.1f}")
    print(f"[saved] {out_path}")

if __name__ == "__main__":
    main()