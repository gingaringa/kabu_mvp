import argparse, json, datetime as dt
from pathlib import Path
import pandas as pd

from src.data.marketdata_mock import load_daily_seed, simulate_minutes_for_date
from src.logic.screener import compute_screen_metrics
from src.logic.signals import compute_orb_signals, size_by_risk

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
LOGDIR = ROOT / "logs"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=str, default=None, help="YYYY-MM-DD（省略時は直近営業日推定）")
    ap.add_argument("--max", type=int, default=5, help="候補の上限")
    ap.add_argument("--min-adv", type=float, default=1e8)
    # スクリーナ追加フィルタ
    ap.add_argument("--min-atr-pct", type=float, default=None)
    ap.add_argument("--max-atr-pct", type=float, default=None)
    ap.add_argument("--gap-min", type=float, default=None)
    ap.add_argument("--gap-max", type=float, default=None)
    # シグナル追加
    ap.add_argument("--or-minutes", type=int, default=5)
    ap.add_argument("--entry-not-before", type=int, default=3)
    ap.add_argument("--spread-limit", type=float, default=0.0005)
    ap.add_argument("--tp-rr", type=float, default=1.0)
    ap.add_argument("--min-stop-ticks", type=int, default=0)
    # デバッグ
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if args.date:
        day = dt.date.fromisoformat(args.date)
    else:
        d = dt.date.today()
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
        day = d

    daily = load_daily_seed(CONFIG / "watchlist_seed.csv", lookback=60)
    metrics = compute_screen_metrics(daily, day, atr_window=20)

    # フィルタ適用
    q = metrics[metrics["adv"] >= args.min_adv].copy()
    if args.min_atr_pct is not None:
        q = q[q["atr_pct"] >= args.min_atr_pct]
    if args.max_atr_pct is not None:
        q = q[q["atr_pct"] <= args.max_atr_pct]
    if args.gap_min is not None:
        q = q[q["gap_pct"] >= args.gap_min]
    if args.gap_max is not None:
        q = q[q["gap_pct"] <= args.gap_max]

    if args.debug:
        print("=== Screener DEBUG ===")
        print(f"All codes       : {len(metrics)}")
        print(f"ADV >= {args.min_adv:g}: {len(metrics[metrics['adv']>=args.min_adv])}")
        if args.min_atr_pct is not None: print(f"ATR% >= {args.min_atr_pct}: {len(metrics[metrics['atr_pct']>=args.min_atr_pct])}")
        if args.max_atr_pct is not None: print(f"ATR% <= {args.max_atr_pct}: {len(metrics[metrics['atr_pct']<=args.max_atr_pct])}")
        if args.gap_min is not None: print(f"Gap% >= {args.gap_min}: {len(metrics[metrics['gap_pct']>=args.gap_min])}")
        if args.gap_max is not None: print(f"Gap% <= {args.gap_max}: {len(metrics[metrics['gap_pct']<=args.gap_max])}")
        print("-- Top by ADV (code, adv, atr%, gap%) --")
        cols = ["code","adv","atr_pct","gap_pct"]
        print(metrics[cols].head(15).to_string(index=False, formatters={
            "adv": lambda x: f"{x:,.0f}",
            "atr_pct": lambda x: f"{x:.2f}",
            "gap_pct": lambda x: f"{x:.2f}",
        }))

    codes = q.sort_values("adv", ascending=False).head(args.max)["code"].astype(str).tolist()
    minutes_map = simulate_minutes_for_date(daily, day)
    risk = json.loads((CONFIG / "risk.json").read_text("utf-8-sig"))

    rows = []
    for code in codes:
        df = minutes_map[code]
        sig = compute_orb_signals(
            df, or_minutes=args.or_minutes, use_vwap=True,
            entry_not_before=args.entry_not_before,
            spread_limit=args.spread_limit,
            tp_rr=args.tp_rr,
            tick_size=risk.get("tick_size", 1.0),
            min_stop_ticks=args.min_stop_ticks
        )
        if sig["entry"] is None:
            continue

        entry_p = sig["entry"]["price"]
        stop_p  = float(sig.get("stop", sig["or_low"]))
        qty = size_by_risk(entry_p, stop_p, risk["capital"], risk["risk_pct"],
                           risk["lot_size"], risk.get("tick_size", 1.0))

        rows.append({
            "code": code, "date": day.isoformat(),
            "entry_time": sig["entry"]["t"], "entry_price": entry_p,
            "stop": stop_p,
            "tp_time":  None if sig["tp"] is None else sig["tp"]["t"],
            "tp_price": None if sig["tp"] is None else sig["tp"]["price"],
            "exit_time": sig["exit"]["t"], "exit_price": sig["exit"]["price"],
            "exit_reason": sig["exit"]["reason"], "qty": qty
        })

    out = pd.DataFrame(rows)
    print("=== PLAN (mock) ===")
    if out.empty:
        print("no entries")
    else:
        print(out[["code","entry_time","entry_price","stop","qty"]])

    LOGDIR.mkdir(exist_ok=True)
    out_path = LOGDIR / f"plan_mock_{day.isoformat()}.csv"
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[saved] {out_path}")

if __name__ == "__main__":
    main()