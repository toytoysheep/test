#!/usr/bin/env python3
"""地方交流重賞予想CLIツール"""
import argparse
import sys
from datetime import date, datetime

from models.race import Race
from scraper.schedule import ScheduleScraper
from scraper.race_card import RaceCardScraper
from storage.db import Database
from predictor.model import Predictor


# ------------------------------------------------------------------ display


def print_race_header(race: Race) -> None:
    print()
    print("=" * 45)
    print("      地方交流重賞予想")
    print("=" * 45)
    print(f"レース名  : {race.race_name} ({race.grade})")
    d = race.race_date
    weekday = "月火水木金土日"[d.weekday()]
    print(f"開催日    : {d.year}年{d.month}月{d.day}日（{weekday}）")
    print(f"競馬場    : {race.baba_name} {race.direction}{race.distance}m")
    if race.start_time:
        print(f"発走時刻  : {race.start_time}")
    print()


def print_predictions(race: Race) -> None:
    print("--- 予想順位 ---")
    ranked = sorted(race.horses, key=lambda h: h.rank)
    for horse in ranked:
        mark = horse.mark
        name = horse.horse_name.ljust(14)
        print(f"{horse.rank}位 {mark} {name}  スコア: {horse.score:5.1f}  偏差値: {horse.deviation_score:4.1f}")
    print()


def print_entries(race: Race) -> None:
    print("--- 出走馬一覧 ---")
    print(f"{'馬番':>3}  {'馬名':<14} {'性齢':>4} {'斤量':>5} {'騎手':<10}")
    print("-" * 50)
    for h in race.horses:
        sex_age = f"{h.sex}{h.age}"
        print(
            f"{h.horse_no:3}  {h.horse_name:<14} {sex_age:>4} "
            f"{h.weight:5.1f} {h.jockey:<10}"
        )
    print()


# ------------------------------------------------------------------ core flow


def run_prediction(race: Race, db: Database, save_html: bool = False) -> None:
    """出馬表取得 → 予想 → 表示 → DB保存 → (HTML出力)"""
    scraper = RaceCardScraper()
    print(f"出馬表を取得中: {race.baba_name} {race.race_no}R ...")

    try:
        race = scraper.fetch_race_card(race)
    except Exception as e:
        print(f"[ERROR] 出馬表の取得に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    if not race.horses:
        print("[WARNING] 出馬表が空です。URLやレース番号を確認してください。")
        sys.exit(1)

    predictor = Predictor(db=db)
    race = predictor.predict(race)

    print_race_header(race)
    print_entries(race)
    print_predictions(race)

    db.save_race(race)
    print(f"[INFO] データを保存しました: {race.race_id}")

    if save_html:
        from reporter import HtmlReporter
        path = HtmlReporter().save(race)
        print(f"[INFO] HTMLを保存しました: {path}")


# ------------------------------------------------------------------ CLI commands


def cmd_next(args, db: Database) -> None:
    """次のダートグレード競走を自動検出して予想"""
    target = date.today()
    if args.date:
        target = parse_date(args.date)

    print(f"ダートグレード競走スケジュールを取得中 ({target.year}年) ...")
    sched = ScheduleScraper()
    try:
        race, is_future = sched.get_next_race(target_date=target)
    except Exception as e:
        print(f"[ERROR] スケジュール取得に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    if not race:
        print(f"[INFO] {target.year}年のダートグレード競走データが見つかりませんでした。")
        sys.exit(0)

    if not is_future:
        print(f"[INFO] {target} 以降の開催予定は見つかりませんでした。直近の過去レースを表示します。")

    print(f"検出: {race.race_name} / {race.race_date} / {race.baba_name}")

    if race.race_no == 0:
        print("[WARNING] レース番号が不明です。--race-no で指定してください。")
        if not args.race_no:
            sys.exit(1)

    if args.race_no:
        race.race_no = args.race_no

    run_prediction(race, db, save_html=args.html)


def cmd_date(args, db: Database) -> None:
    """日付指定で予想"""
    target = parse_date(args.date)

    if not args.baba_code:
        print("[ERROR] --baba-code が必要です。", file=sys.stderr)
        sys.exit(1)

    if not args.race_no:
        print("[ERROR] --race-no が必要です。", file=sys.stderr)
        sys.exit(1)

    race = Race(
        race_date=target,
        baba_code=args.baba_code,
        race_no=args.race_no,
    )
    run_prediction(race, db, save_html=args.html)


def cmd_list(args) -> None:
    """今後のダートグレード競走一覧を表示"""
    today = date.today()
    if args.date:
        today = parse_date(args.date)

    print(f"ダートグレード競走スケジュールを取得中 ({today.year}年) ...")
    sched = ScheduleScraper()
    try:
        races = sched.fetch_schedule(today.year)
        if today.month >= 11:
            races += sched.fetch_schedule(today.year + 1)
    except Exception as e:
        print(f"[ERROR] スケジュール取得に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    future = sorted(
        [r for r in races if r.race_date >= today],
        key=lambda r: r.race_date,
    )

    if not future:
        print(f"[INFO] {today} 以降の開催予定は見つかりませんでした。")
        sys.exit(0)

    weekdays = "月火水木金土日"
    grade_order = {"Jpn1": 0, "G1": 0, "Jpn2": 1, "G2": 1, "Jpn3": 2, "G3": 2}
    grade_marks = {"Jpn1": "★★★", "G1": "★★★", "Jpn2": "★★ ", "G2": "★★ ", "Jpn3": "★  ", "G3": "★  "}

    print()
    print(f"  今後のダートグレード競走一覧（{today} 以降・{len(future)}件）")
    print("  " + "─" * 62)
    print(f"  {'日付':<12} {'グレード':<6} {'競馬場':<8} {'距離':>6}  レース名")
    print("  " + "─" * 62)

    prev_month = None
    for r in future:
        month = r.race_date.month
        if month != prev_month:
            if prev_month is not None:
                print()
            print(f"  ── {r.race_date.year}年 {month}月 ──")
            prev_month = month

        wd = weekdays[r.race_date.weekday()]
        date_str = f"{r.race_date.month}/{r.race_date.day}（{wd}）"
        grade_str = r.grade or "－"
        star = grade_marks.get(r.grade, "   ")
        dist_str = f"{r.distance}m" if r.distance else "－"
        time_str = f" {r.start_time}" if r.start_time else ""

        # 本日開催には「◀今日」マーカー
        today_mark = " ★本日" if r.race_date == date.today() else ""

        print(
            f"  {date_str:<12} {star} {grade_str:<5}  {r.baba_name:<7}"
            f" {dist_str:>5}  {r.race_name}{time_str}{today_mark}"
        )

    print("  " + "─" * 62)
    print(f"  計 {len(future)} レース")
    print()


# ------------------------------------------------------------------ helpers


def parse_date(date_str: str) -> date:
    for fmt in ("%Y%m%d", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    print(f"[ERROR] 日付形式が不正です: {date_str}  (例: 20260505)", file=sys.stderr)
    sys.exit(1)


# ------------------------------------------------------------------ main


def main() -> None:
    parser = argparse.ArgumentParser(
        description="地方交流重賞（ダートグレード競走）予想ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 今後のダートグレード競走一覧を表示
  python main.py --list

  # 基準日以降の一覧を表示
  python main.py --list --date 20260601

  # 次に開催されるダートグレード競走を自動検出して予想
  python main.py --next

  # HTML形式でも出力する
  python main.py --next --html

  # 基準日を指定して次のレースを検出
  python main.py --next --date 20260505

  # 競馬場・レース番号を直接指定して予想
  python main.py --date 20260505 --baba-code 19 --race-no 11

競馬場コード:
  3=帯広  10=盛岡  14=水沢  19=船橋  20=大井  21=川崎
  22=金沢  24=名古屋  27=園田  28=姫路  31=高知  32=佐賀  36=門別
        """,
    )

    parser.add_argument(
        "--list", action="store_true",
        help="今後のダートグレード競走一覧を表示する",
    )
    parser.add_argument(
        "--next", action="store_true",
        help="次のダートグレード競走を自動検出して予想する",
    )
    parser.add_argument(
        "--date", type=str, metavar="YYYYMMDD",
        help="日付を指定（例: 20260505）",
    )
    parser.add_argument(
        "--baba-code", type=str, metavar="CODE",
        help="競馬場コード（例: 19=船橋）",
    )
    parser.add_argument(
        "--race-no", type=int, metavar="N",
        help="レース番号",
    )
    parser.add_argument(
        "--html", action="store_true",
        help="予想結果を output/ フォルダに HTML ファイルとして保存する",
    )
    parser.add_argument(
        "--db", type=str, default=None, metavar="PATH",
        help="DBファイルパス（デフォルト: data/races.db）",
    )

    args = parser.parse_args()

    db_path = None
    if args.db:
        from pathlib import Path
        db_path = Path(args.db)

    if args.list:
        cmd_list(args)
        sys.exit(0)

    with Database(db_path) if db_path else Database() as db:
        if args.next:
            cmd_next(args, db)
        elif args.date and args.baba_code and args.race_no:
            cmd_date(args, db)
        elif args.date and not args.baba_code:
            cmd_next(args, db)
        else:
            parser.print_help()
            sys.exit(0)


if __name__ == "__main__":
    main()
