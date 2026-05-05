"""ダートグレード競走スケジュール取得"""
import re
from datetime import date
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from models.race import Race, BABA_CODE_MAP

_BABA_NAME_TO_CODE: dict[str, str] = {v: k for k, v in BABA_CODE_MAP.items()}

_GRADE_CLASS_MAP: dict[str, str] = {
    "jpn1": "Jpn1", "jpn2": "Jpn2", "jpn3": "Jpn3",
    "g1": "G1", "g2": "G2", "g3": "G3",
}

BASE_URL = "https://www.keiba.go.jp/dirtgraderace/{year}/racelist/index.html"
NAR_HOST = "https://www.keiba.go.jp"


class ScheduleScraper:
    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

    def _get(self, url: str) -> BeautifulSoup:
        with httpx.Client(timeout=self._timeout, headers=self._headers, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    # ------------------------------------------------------------------ schedule

    def fetch_schedule(self, year: int) -> list[Race]:
        """指定年のNAR地方交流重賞一覧を取得する"""
        url = BASE_URL.format(year=year)
        soup = self._get(url)
        return self._parse_schedule(soup, year)

    def _parse_schedule(self, soup: BeautifulSoup, year: int) -> list[Race]:
        """
        実際のHTML構造:
          <div class="month">
            <h3 class="h"><span class="year">2026年</span><span>5</span>月</h3>
            <ul>
              <li class="js-item" data-cate="..." data-subcate="...">
                <a href="/dirtgraderace/2026/0505_kashiwakinen/racecard.html">
                  <p>5月5日(祝火)</p>
                  <h4 class="jpn1">かしわ記念</h4>
                  <p>船橋 左1600m 20:05発走</p>
                </a>
              </li>
            </ul>
          </div>
        """
        races: list[Race] = []

        for month_div in soup.select("div.month"):
            h3 = month_div.select_one("h3.h")
            if not h3:
                continue
            month_match = re.search(r"(\d+)\s*月", h3.get_text())
            if not month_match:
                continue
            month = int(month_match.group(1))

            for li in month_div.select("li.js-item"):
                race = self._parse_li(li, year, month)
                if race:
                    races.append(race)

        return races

    def _parse_li(self, li, year: int, month: int) -> Optional[Race]:
        try:
            a = li.select_one("a")
            if not a:
                return None

            href = a.get("href", "")
            # JRAレース（外部リンク）はスキップ
            if "jra.go.jp" in href:
                return None
            # NAR内部リンクのみ対象
            if not href.startswith("/dirtgraderace/"):
                return None

            ps = a.find_all("p")
            h4 = a.find("h4")
            if not ps or not h4:
                return None

            # 日付: "5月5日(祝火)" → day抽出
            day_match = re.search(r"(\d+)日", ps[0].get_text())
            if not day_match:
                return None
            race_date = date(year, month, int(day_match.group(1)))

            race_name = h4.get_text(strip=True)
            grade = self._grade_from_class(h4.get("class") or [])

            # コース情報: "船橋 左1600m 20:05発走" or "船橋 左1600m 20:05発走予定"
            track_text = ps[1].get_text(strip=True) if len(ps) > 1 else ""
            baba_name, direction, distance, start_time = self._parse_track_info(track_text)

            baba_code = self._resolve_baba_code(baba_name)
            if not baba_code:
                return None

            racecard_url = NAR_HOST + href

            return Race(
                race_date=race_date,
                baba_code=baba_code,
                race_no=0,
                race_name=race_name,
                grade=grade,
                distance=distance,
                direction=direction,
                start_time=start_time,
                racecard_url=racecard_url,
            )
        except (ValueError, IndexError, AttributeError):
            return None

    # ------------------------------------------------------------------ race_no resolution

    def resolve_race_no(self, race: Race) -> Race:
        """racecard.htmlを取得してKeibaWeb DebaTable URLからrace_noを解決する"""
        if not race.racecard_url or race.race_no != 0:
            return race

        try:
            soup = self._get(race.racecard_url)
        except Exception:
            return race

        # DebaTable リンクを探す: ?k_raceDate=...&k_raceNo=11&k_babaCode=19
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "DebaTable" not in href:
                continue
            no_m = re.search(r"k_raceNo=(\d+)", href)
            bc_m = re.search(r"k_babaCode=(\d+)", href)
            if no_m:
                race.race_no = int(no_m.group(1))
            if bc_m:
                race.baba_code = bc_m.group(1)
            break

        return race

    # ------------------------------------------------------------------ helpers

    def _grade_from_class(self, classes: list) -> str:
        for c in classes:
            g = _GRADE_CLASS_MAP.get(c.lower())
            if g:
                return g
        return ""

    def _parse_track_info(self, text: str) -> tuple[str, str, int, str]:
        """
        "船橋 左1600m 20:05発走" → ("船橋", "左", 1600, "20:05")
        "名古屋 右2100m 18:05発走予定" → ("名古屋", "右", 2100, "18:05")
        """
        parts = text.split()
        baba_name = parts[0] if parts else ""
        direction = ""
        distance = 0
        start_time = ""

        for part in parts[1:]:
            m = re.match(r"([左右直]?)(\d{3,4})m", part)
            if m:
                direction = m.group(1)
                distance = int(m.group(2))
            tm = re.search(r"(\d{1,2}:\d{2})", part)
            if tm:
                start_time = tm.group(1)

        return baba_name, direction, distance, start_time

    def _resolve_baba_code(self, name: str) -> Optional[str]:
        if not name:
            return None
        if name in _BABA_NAME_TO_CODE:
            return _BABA_NAME_TO_CODE[name]
        for full_name, code in _BABA_NAME_TO_CODE.items():
            # 帯広（ばんえい）の場合に"帯広"で部分一致させる
            if name in full_name:
                return code
        return None

    # ------------------------------------------------------------------ next race

    def get_next_race(
        self, target_date: Optional[date] = None
    ) -> tuple[Optional[Race], bool]:
        """target_date 以降で最初に開催されるダートグレード競走を返す。

        Returns:
            (race, is_future):
              is_future=True  → 当日または将来のレース
              is_future=False → 未来が見つからず直近の過去レースを返した場合
              race=None       → データが全くない場合
        """
        today = target_date or date.today()
        year = today.year

        races = self.fetch_schedule(year)
        # 11月以降は翌年スケジュールも確認する
        if today.month >= 11 and (not races or all(r.race_date < today for r in races)):
            races += self.fetch_schedule(year + 1)

        if not races:
            return None, False

        future = [r for r in races if r.race_date >= today]
        if future:
            future.sort(key=lambda r: (r.race_date, r.race_no))
            race = future[0]
            race = self.resolve_race_no(race)
            return race, True

        # フォールバック: 直近の過去レース
        past = sorted(races, key=lambda r: r.race_date, reverse=True)
        race = past[0]
        race = self.resolve_race_no(race)
        return race, False
