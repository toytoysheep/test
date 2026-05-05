"""競馬新聞風 HTML レポート生成"""
import html as _html
from datetime import datetime
from pathlib import Path

from models.race import Race
from models.horse import Horse

OUTPUT_DIR = Path(__file__).parent.parent / "output"

# 枠番カラー（日本中央競馬会標準色）
_FRAME_COLORS: dict[int, tuple[str, str]] = {
    1: ("#FFFFFF", "#222222"),   # 白枠  bg / text
    2: ("#000000", "#FFFFFF"),   # 黒枠
    3: ("#CC0000", "#FFFFFF"),   # 赤枠
    4: ("#3355CC", "#FFFFFF"),   # 青枠
    5: ("#FFDD00", "#222222"),   # 黄枠
    6: ("#009933", "#FFFFFF"),   # 緑枠
    7: ("#FF8800", "#FFFFFF"),   # 橙枠
    8: ("#FF69B4", "#222222"),   # 桃枠
}

_MARKS = {1: "◎", 2: "○", 3: "▲", 4: "△", 5: "×"}


def _e(s: object) -> str:
    """HTML エスケープ"""
    return _html.escape(str(s))


def _frame_style(frame_no: int) -> str:
    bg, fg = _FRAME_COLORS.get(frame_no, ("#EEEEEE", "#222222"))
    return f"background:{bg};color:{fg};font-weight:bold;"


def _mark_color(rank: int) -> str:
    colors = {1: "#CC0000", 2: "#0055CC", 3: "#007700", 4: "#888800", 5: "#666666"}
    return colors.get(rank, "#333333")


def _score_bar(score: float) -> str:
    w = max(2, int(score))
    color = "#CC2200" if score >= 60 else "#0055BB" if score >= 40 else "#558800"
    return (
        f'<div class="score-bar-wrap">'
        f'<div class="score-bar" style="width:{w}%;background:{color}"></div>'
        f'<span class="score-num">{score:.1f}</span>'
        f'</div>'
    )


def _past_badge(pos: int) -> str:
    if pos == 0:
        return '<span class="past-pos past-unk">-</span>'
    color = (
        "#CC2200" if pos == 1 else
        "#0055BB" if pos == 2 else
        "#007700" if pos == 3 else
        "#888888"
    )
    return f'<span class="past-pos" style="border-color:{color};color:{color}">{pos}</span>'


def _render_past(horse: Horse, n: int = 5) -> str:
    if not horse.past_races:
        return '<span class="no-data">データなし</span>'
    parts = []
    for pr in horse.past_races[:n]:
        tip = _e(f"{pr.race_date} {pr.baba_name} {pr.race_name} {pr.distance}m")
        parts.append(f'<span title="{tip}">{_past_badge(pr.finishing_pos)}</span>')
    return "".join(parts)


class HtmlReporter:
    def __init__(self, output_dir: Path = OUTPUT_DIR):
        self._dir = output_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, race: Race) -> Path:
        """HTML を生成してファイルに保存し、パスを返す"""
        filename = f"{race.race_date.strftime('%Y%m%d')}_{race.baba_code}R{race.race_no}.html"
        path = self._dir / filename
        path.write_text(self._render(race), encoding="utf-8")
        return path

    # ------------------------------------------------------------------ render

    def _render(self, race: Race) -> str:
        weekday = "月火水木金土日"[race.race_date.weekday()]
        date_str = f"{race.race_date.year}年{race.race_date.month}月{race.race_date.day}日（{weekday}）"
        generated = datetime.now().strftime("%Y/%m/%d %H:%M")

        rows_html = "\n".join(self._horse_row(h) for h in sorted(race.horses, key=lambda h: h.rank or 99))

        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(race.race_name)} 予想 | NAR重賞予想</title>
{_CSS}
</head>
<body>
<div class="page">

  <header class="race-header">
    <div class="grade-badge grade-{race.grade.lower().replace('jpn','jpn')}">{_e(race.grade)}</div>
    <h1 class="race-title">{_e(race.race_name)}</h1>
    <div class="race-meta">
      <span>📅 {_e(date_str)}</span>
      <span>🏟 {_e(race.baba_name)}</span>
      <span>📏 {_e(race.direction)}ダート {_e(race.distance)}m</span>
      {"<span>🕐 " + _e(race.start_time) + " 発走</span>" if race.start_time else ""}
    </div>
  </header>

  <div class="legend">
    <span class="legend-item"><span class="mark" style="color:#CC0000">◎</span> 本命</span>
    <span class="legend-item"><span class="mark" style="color:#0055CC">○</span> 対抗</span>
    <span class="legend-item"><span class="mark" style="color:#007700">▲</span> 単穴</span>
    <span class="legend-item"><span class="mark" style="color:#888800">△</span> 連下</span>
    <span class="legend-item"><span class="mark" style="color:#666666">×</span> 注意</span>
  </div>

  <div class="table-wrap">
  <table class="race-table">
    <thead>
      <tr>
        <th class="col-rank">印</th>
        <th class="col-frame">枠</th>
        <th class="col-no">馬番</th>
        <th class="col-name">馬名</th>
        <th class="col-info">性齢</th>
        <th class="col-weight">斤量</th>
        <th class="col-jockey">騎手</th>
        <th class="col-trainer">調教師</th>
        <th class="col-odds">オッズ</th>
        <th class="col-past">近走成績</th>
        <th class="col-score">スコア</th>
      </tr>
    </thead>
    <tbody>
{rows_html}
    </tbody>
  </table>
  </div>

  <section class="detail-section">
    <h2>詳細データ</h2>
    <div class="detail-grid">
{"".join(self._detail_card(h) for h in sorted(race.horses, key=lambda h: h.rank or 99))}
    </div>
  </section>

  <footer class="page-footer">
    生成日時: {_e(generated)} ／ NAR地方交流重賞予想ツール（統計スコアリング）
  </footer>
</div>
</body>
</html>"""

    def _horse_row(self, horse: Horse) -> str:
        rank = horse.rank or 0
        mark = _MARKS.get(rank, "")
        mark_html = f'<span class="mark" style="color:{_mark_color(rank)}">{_e(mark)}</span>' if mark else ""
        frame_style = _frame_style(horse.frame_no)
        highlight = ' class="row-top"' if rank == 1 else (' class="row-noted"' if rank <= 3 else "")
        sex_age = f"{_e(horse.sex)}{_e(horse.age)}" if horse.sex else "－"
        weight_str = f"{horse.weight:.1f}" if horse.weight else "－"
        odds_str = f"{horse.odds:.1f}" if horse.odds else "－"
        if horse.popularity:
            odds_str += f'<br><span class="popularity">({horse.popularity}人気)</span>'

        return f"""      <tr{highlight}>
        <td class="col-rank">{mark_html}</td>
        <td class="col-frame"><span class="frame-badge" style="{frame_style}">{_e(horse.frame_no) if horse.frame_no else "－"}</span></td>
        <td class="col-no">{_e(horse.horse_no)}</td>
        <td class="col-name"><span class="horse-name">{_e(horse.horse_name)}</span></td>
        <td class="col-info">{sex_age}</td>
        <td class="col-weight">{weight_str}</td>
        <td class="col-jockey">{_e(horse.jockey) or "－"}</td>
        <td class="col-trainer">{_e(horse.trainer) or "－"}</td>
        <td class="col-odds">{odds_str}</td>
        <td class="col-past">{_render_past(horse)}</td>
        <td class="col-score">{_score_bar(horse.score)}</td>
      </tr>"""

    def _detail_card(self, horse: Horse) -> str:
        rank = horse.rank or 0
        mark = _MARKS.get(rank, "")
        mark_color = _mark_color(rank)
        frame_style = _frame_style(horse.frame_no)

        past_rows = ""
        for pr in horse.past_races[:5]:
            pos_badge = _past_badge(pr.finishing_pos)
            past_rows += (
                f'<tr><td>{pos_badge}</td>'
                f'<td>{_e(pr.race_date)}</td>'
                f'<td>{_e(pr.baba_name)}</td>'
                f'<td>{_e(pr.race_name)}</td>'
                f'<td>{pr.distance}m</td></tr>'
            )

        past_table = (
            f'<table class="past-table"><thead><tr>'
            f'<th>着順</th><th>日付</th><th>競馬場</th><th>レース名</th><th>距離</th>'
            f'</tr></thead><tbody>{past_rows}</tbody></table>'
            if past_rows else '<p class="no-data">過去成績データなし</p>'
        )

        return f"""      <div class="detail-card">
        <div class="detail-header">
          <span class="frame-badge" style="{frame_style}">{horse.frame_no}</span>
          <span class="detail-no">{horse.horse_no}番</span>
          <span class="mark detail-mark" style="color:{mark_color}">{_e(mark)}</span>
          <span class="detail-name">{_e(horse.horse_name)}</span>
          <span class="detail-score">スコア {horse.score:.1f}</span>
        </div>
        <div class="detail-body">
          <div class="detail-info">
            <span>性齢: {_e(horse.sex)}{_e(horse.age)}</span>
            <span>斤量: {horse.weight:.1f}kg</span>
            <span>騎手: {_e(horse.jockey) or "－"}</span>
            <span>調教師: {_e(horse.trainer) or "－"}</span>
            {"<span>オッズ: " + str(horse.odds) + "倍 (" + str(horse.popularity) + "人気)</span>" if horse.odds else ""}
          </div>
          {past_table}
        </div>
      </div>"""


# ------------------------------------------------------------------ CSS

_CSS = """<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: "Hiragino Kaku Gothic ProN", "Meiryo", "YuGothic", sans-serif;
  background: #1a1a2e;
  color: #eee;
  font-size: 14px;
}
.page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px;
}

/* ---- Header ---- */
.race-header {
  background: linear-gradient(135deg, #0d0d1a 0%, #16213e 60%, #0f3460 100%);
  border: 2px solid #e94560;
  border-radius: 10px;
  padding: 20px 24px;
  margin-bottom: 12px;
  text-align: center;
}
.grade-badge {
  display: inline-block;
  padding: 3px 12px;
  border-radius: 20px;
  font-weight: bold;
  font-size: 13px;
  margin-bottom: 8px;
  letter-spacing: 1px;
}
.grade-jpn1, .grade-g1 { background: #b8860b; color: #fff; border: 1px solid #ffd700; }
.grade-jpn2, .grade-g2 { background: #888; color: #fff; border: 1px solid #ccc; }
.grade-jpn3, .grade-g3 { background: #8b4513; color: #fff; border: 1px solid #cd853f; }
.grade-badge:not([class*="grade-jpn"]):not([class*="grade-g"]) { background: #444; color: #ccc; }

.race-title {
  font-size: 28px;
  font-weight: bold;
  color: #fff;
  letter-spacing: 2px;
  margin-bottom: 10px;
}
.race-meta {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 16px;
  color: #aac4ff;
  font-size: 13px;
}
.race-meta span { display: flex; align-items: center; gap: 4px; }

/* ---- Legend ---- */
.legend {
  display: flex;
  gap: 16px;
  padding: 8px 16px;
  background: #16213e;
  border-radius: 6px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.legend-item { display: flex; align-items: center; gap: 4px; font-size: 13px; color: #ccc; }
.mark { font-size: 18px; font-weight: bold; line-height: 1; }

/* ---- Table ---- */
.table-wrap { overflow-x: auto; margin-bottom: 24px; }
.race-table {
  width: 100%;
  border-collapse: collapse;
  background: #0d1b2a;
  border-radius: 8px;
  overflow: hidden;
  min-width: 820px;
}
.race-table thead tr {
  background: #0f3460;
  color: #aac4ff;
  font-size: 12px;
  text-align: center;
}
.race-table th {
  padding: 8px 6px;
  border-bottom: 2px solid #e94560;
  white-space: nowrap;
}
.race-table tbody tr {
  border-bottom: 1px solid #1e3a5a;
  transition: background 0.15s;
}
.race-table tbody tr:hover { background: #1a3050; }
.race-table tbody tr.row-top {
  background: linear-gradient(90deg, #2a0a0a 0%, #1a0808 100%);
  border-left: 3px solid #e94560;
}
.race-table tbody tr.row-noted {
  background: #0f1e30;
  border-left: 3px solid #3a7bd5;
}
.race-table td {
  padding: 7px 6px;
  vertical-align: middle;
  text-align: center;
}

/* Columns */
.col-rank  { width: 32px; font-size: 20px; }
.col-frame { width: 36px; }
.col-no    { width: 36px; color: #aaa; }
.col-name  { text-align: left; padding-left: 8px; }
.col-info  { width: 48px; }
.col-weight { width: 48px; }
.col-jockey { width: 80px; white-space: nowrap; }
.col-trainer { width: 80px; white-space: nowrap; font-size: 12px; color: #aaa; }
.col-odds  { width: 70px; }
.col-past  { width: 110px; }
.col-score { width: 130px; }

.horse-name { font-weight: bold; font-size: 15px; color: #fff; }
.frame-badge {
  display: inline-block;
  width: 26px; height: 26px;
  line-height: 26px;
  text-align: center;
  border-radius: 4px;
  font-size: 13px;
}
.popularity { font-size: 11px; color: #aaa; }

/* Score bar */
.score-bar-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}
.score-bar {
  height: 8px;
  border-radius: 4px;
  flex-shrink: 0;
  max-width: 80px;
}
.score-num { font-size: 13px; font-weight: bold; color: #fff; white-space: nowrap; }

/* Past pos badges */
.past-pos {
  display: inline-block;
  width: 20px; height: 20px;
  line-height: 18px;
  text-align: center;
  border: 1.5px solid #888;
  border-radius: 3px;
  font-size: 11px;
  font-weight: bold;
  color: #888;
  margin: 0 1px;
}
.past-unk { border-color: #444; color: #444; }
.no-data { color: #555; font-size: 12px; }

/* ---- Detail Section ---- */
.detail-section h2 {
  font-size: 16px;
  color: #aac4ff;
  border-bottom: 1px solid #0f3460;
  padding-bottom: 6px;
  margin-bottom: 14px;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.detail-card {
  background: #0d1b2a;
  border: 1px solid #1e3a5a;
  border-radius: 8px;
  overflow: hidden;
}
.detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #0f3460;
}
.detail-no { color: #aaa; font-size: 12px; }
.detail-mark { font-size: 20px; }
.detail-name { font-weight: bold; font-size: 15px; color: #fff; flex: 1; }
.detail-score { font-size: 13px; color: #ffd700; font-weight: bold; white-space: nowrap; }
.detail-body { padding: 10px 12px; }
.detail-info {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 12px;
  color: #aaa;
}
.past-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.past-table th {
  background: #0a1628;
  color: #778ca3;
  padding: 3px 5px;
  text-align: center;
  border-bottom: 1px solid #1e3a5a;
}
.past-table td {
  padding: 3px 5px;
  text-align: center;
  border-bottom: 1px solid #111d2e;
  color: #ccc;
}
.past-table tr:last-child td { border-bottom: none; }

/* ---- Footer ---- */
.page-footer {
  text-align: center;
  color: #555;
  font-size: 11px;
  padding: 16px 0;
  border-top: 1px solid #1e3a5a;
}
</style>"""
