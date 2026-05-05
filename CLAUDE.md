# CLAUDE.md

## 許可設定

```json
{
  "permissions": {
    "allow": [
      "PowerShell(*)",
      "Bash(*)"
    ]
  }
}
```

---

## プロジェクト概要

**NAR地方交流重賞予想ツール**（`nar_graded_predictor/`）

NAR公式サイト（keiba.go.jp）をスクレイピングし、ダートグレード競走の出馬表を取得して統計スコアリングで予想を行うCLIツール。

### 技術スタック

| ライブラリ | 用途 |
|---|---|
| Python 3.11+ | 実行環境 |
| httpx | HTTPリクエスト |
| beautifulsoup4 + lxml | HTMLパース |
| sqlite3 | データ保存（標準ライブラリ） |
| pyyaml | 設定ファイル読み込み |

### ディレクトリ構成

```
nar_graded_predictor/
├── main.py              # CLIエントリーポイント
├── config.yaml          # 予想スコアの重みパラメータ
├── models/
│   ├── race.py          # Race データクラス・競馬場コード表
│   └── horse.py         # Horse / PastRace データクラス
├── scraper/
│   ├── schedule.py      # NARスケジュール取得・次走検出
│   └── race_card.py     # DebaTable 出馬表スクレイピング
├── storage/
│   └── db.py            # SQLite 保存・読み込み・騎手成績集計
├── predictor/
│   └── model.py         # 統計スコアリング（config.yaml 参照）
├── reporter/
│   └── html.py          # 競馬新聞風 HTML レポート生成
├── data/
│   └── races.db         # SQLite DB（自動生成）
└── output/              # HTML出力先（自動生成）
```

### スクレイピング対象 URL

```
# 年間ダートグレード競走一覧
https://www.keiba.go.jp/dirtgraderace/{year}/racelist/index.html

# レースカード（race_no 解決に使用）
https://www.keiba.go.jp/dirtgraderace/{year}/{MMDD_racename}/racecard.html

# 出馬表
https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/DebaTable
  ?k_raceDate=YYYY/MM/DD&k_babaCode=XX&k_raceNo=X
```

### 競馬場コード

| コード | 競馬場 | コード | 競馬場 |
|---|---|---|---|
| 3 | 帯広（ばんえい） | 24 | 名古屋 |
| 10 | 盛岡 | 27 | 園田 |
| 14 | 水沢 | 28 | 姫路 |
| 19 | 船橋 | 31 | 高知 |
| 20 | 大井 | 32 | 佐賀 |
| 21 | 川崎 | 36 | 門別 |
| 22 | 金沢 | | |

### 予想スコアリング（`config.yaml` で重み変更可能）

| 指標 | デフォルト重み | 内容 |
|---|---|---|
| 前走着順 | 20.0 | 1着=満点、着順が下がるほど減点 |
| 距離変化 | 10.0 | ±200m以内で加点（前走データ必須） |
| 騎手の交流重賞実績 | 15.0 | 勝率×0.6 + 3着内率×0.4 |
| 斤量 | 8.0 | 56kg基準、軽いほど有利 |
| 同競馬場実績 | 12.0 | 同競馬場での勝率 |

---

## セットアップ

```powershell
# 依存ライブラリのインストール
cd nar_graded_predictor
pip install -r requirements.txt
```

---

## よく使うコマンド

```powershell
# 今後のダートグレード競走一覧を表示
python main.py --list

# 基準日以降の一覧を表示
python main.py --list --date 20260601

# 次に開催されるダートグレード競走を自動検出して予想
python main.py --next

# HTML形式でも出力する（output/ フォルダに保存）
python main.py --next --html

# 基準日を指定して次のレースを検出
python main.py --next --date 20260505

# 日付・競馬場・レース番号を直接指定
python main.py --date 20260505 --baba-code 19 --race-no 11

# 上記 + HTML出力
python main.py --date 20260505 --baba-code 19 --race-no 11 --html

# 別のDBファイルを使用
python main.py --next --db path/to/custom.db

# ヘルプ
python main.py --help
```

---

## 注意事項

- **スクレイピング対象** は NAR 公式サイト（keiba.go.jp）のみ。JRA レースはスキップされる。
- **race_no** はスケジュール一覧には含まれないため、`racecard.html` を追加取得して解決する。取得できない場合は `--race-no` で手動指定。
- **出馬表** は枠順発表（通常レース2〜3日前）以降でないと取得できない。
- **騎手の交流重賞実績** はローカル DB に蓄積されたデータに基づくため、初回実行時はスコアに反映されない。
- DB スキーマは起動時に自動マイグレーションされる（`ALTER TABLE` で列追加）。
