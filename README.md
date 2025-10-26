# kabu_mvp

## 目標
- 寄り直後の **Opening Range Breakout + VWAP** ロジックで自動判定
- 1トレードの口座リスク: isk_pct (デフォルト0.5%)

## 毎朝
1. conda activate kabu / cd C:\stocks\kabu_mvp
2. （モック運転）python -m app.run_mock --date YYYY-MM-DD --max 5
3. （本番に切替後）python -m app.run_live   ← 11/1以降

## ポジション管理
- 同時最大: max_positions
- 1日最大損失: 口座の 1%
- ログ: logs/ に CSV で保存

## 差し替えポリシー
- **本番切替で差し替えるのは「データ取得層のみ」**
  - モック: src\data\marketdata_mock.py
  - 本番:   src\data\kabu_client.py（11/1に実装・使用）
- スクリーニング/シグナル/サイジングのロジックは**同じ**で動きます。