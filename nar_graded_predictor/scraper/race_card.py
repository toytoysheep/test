"""出馬表スクレイピング（DebaTable）"""
import re
from copy import copy
from datetime import date
from typing import Optional

import httpx
from bs4 import BeautifulSoup, Tag

from models.race import Race
from models.horse import Horse, PastRace

DEBATABLE_URL = (
    "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/DebaTable"
    "?k_raceDate={date}&k_babaCode={baba}&k_raceNo={race_no}"
)


class RaceCardScraper:
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
        with httpx.Client(
            timeout=self._timeout, headers=self._headers, follow_redirects=True
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    def fetch_race_card(self, race: Race) -> Race:
        """出馬表を取得して race.horses を埋める"""
        url = DEBATABLE_URL.format(
            date=race.race_date.strftime("%Y/%m/%d"),
            baba=race.baba_code,
            race_no=race.race_no,
        )
        soup = self._get(url)
        self._fill_race_info(soup, race)
        race.horses = self._parse_horses(soup, race)
        return race

    # ------------------------------------------------------------------ race header

    def _fill_race_info(self, soup: BeautifulSoup, race: Race) -> None:
        page_text = soup.get_text(" ")

        if not race.start_time:
            m = re.search(r"(\d{1,2}:\d{2})", page_text)
            if m:
                race.start_time = m.group(1)

        if not race.distance:
            m = re.search(r"(\d{3,4})\s*m", page_text, re.IGNORECASE)
            if m:
                race.distance = int(m.group(1))

        if not race.direction:
            for d in ("左", "右", "直線"):
                if d in page_text:
                    race.direction = d
                    break

    # ------------------------------------------------------------------ horses

    def _parse_horses(self, soup: BeautifulSoup, race: Race) -> list[Horse]:
        """
        1頭 = 5行のspanブロック構造:
          行0 (tBorder): 枠番(rowspan5), 馬番(rowspan5), 馬名, 騎手,
                         オッズ(rowspan2), 着別成績(rowspan5), 前走〜5走前raceInfo
          行1: 性齢(noBorder), 毛色(noBorder), 生年月日, 斤量+成績,
               前走〜5走前 race link
          行2: 父名, 調教師, odds_weight(rowspan2),
               前走〜5走前 人気+馬体重+騎手+斤量
          行3: 母父名, 馬主, 前走〜5走前 タイム
          行4: 血統, 生産牧場
        """
        horses: list[Horse] = []

        for name_a in soup.find_all("a", class_="horseName"):
            row0 = name_a.find_parent("tr")
            if not row0:
                continue

            # 5行を収集
            rows: list[Tag] = [row0]
            sib = row0
            for _ in range(4):
                sib = sib.find_next_sibling("tr")
                if sib:
                    rows.append(sib)

            horse = self._parse_horse_rows(rows, race)
            if horse:
                horses.append(horse)

        return horses

    def _parse_horse_rows(self, rows: list[Tag], race: Race) -> Optional[Horse]:
        row0 = rows[0]

        # ---- 枠番
        frame_td = row0.find("td", class_=lambda c: c and "courseNum" in c)
        frame_no = int(frame_td.get_text(strip=True)) if frame_td else 0

        # ---- 馬番
        horse_no_td = row0.find("td", class_="horseNum")
        if not horse_no_td:
            return None
        horse_no_text = horse_no_td.get_text(strip=True)
        if not horse_no_text.isdigit():
            return None
        horse_no = int(horse_no_text)

        # ---- 馬名
        name_a = row0.find("a", class_="horseName")
        horse_name = name_a.get_text(strip=True) if name_a else ""

        # ---- 騎手（（JRA）などの所属表記を除去）
        jockey_a = row0.find("a", class_="jockeyName")
        jockey = ""
        if jockey_a:
            tmp = copy(jockey_a)
            for sp in tmp.find_all("span", class_="jockeyarea"):
                sp.decompose()
            jockey = tmp.get_text(strip=True)

        # ---- オッズ・人気
        odds: Optional[float] = None
        popularity: Optional[int] = None
        odds_span = row0.find("span", class_="odds")
        if odds_span:
            try:
                odds = float(odds_span.get_text(strip=True))
            except ValueError:
                pass
        odds_td = row0.find("td", class_="odds_weight")
        if odds_td:
            pop_m = re.search(r"(\d+)人気", odds_td.get_text())
            if pop_m:
                popularity = int(pop_m.group(1))

        # ---- 性齢・斤量（行1）
        sex, age, weight = "", 0, 0.0
        if len(rows) > 1:
            row1 = rows[1]
            noborder = row1.find_all("td", class_="noBorder")
            if noborder:
                sa = noborder[0].get_text(strip=True)  # "牡8"
                sex = sa[0] if sa else ""
                am = re.search(r"(\d+)", sa)
                age = int(am.group(1)) if am else 0

            # 斤量は "57.0　12-1-4-6" の形式のセルから取得
            for td in row1.find_all("td"):
                wm = re.match(r"(\d{2,3}\.\d)", td.get_text(strip=True))
                if wm:
                    try:
                        weight = float(wm.group(1))
                        break
                    except ValueError:
                        pass

        # ---- 調教師（行2）
        trainer = ""
        if len(rows) > 2:
            ta = rows[2].find("a", href=lambda h: h and "TrainerMark" in h)
            if ta:
                trainer = re.sub(r"[（(].*?[）)]", "", ta.get_text(strip=True)).strip()

        # ---- 前走情報（行0の raceInfo div × 最大5走）
        past_races: list[PastRace] = []
        race_infos = row0.find_all("div", class_="raceInfo")
        race_links = rows[1].find_all("a", class_="race") if len(rows) > 1 else []
        past_cells_row2 = self._get_past_data_cells(rows[2]) if len(rows) > 2 else []

        for i, info_div in enumerate(race_infos):
            pr = self._parse_past_race(
                info_div,
                race_links[i] if i < len(race_links) else None,
                past_cells_row2[i] if i < len(past_cells_row2) else "",
                race,
            )
            if pr:
                past_races.append(pr)

        return Horse(
            horse_no=horse_no,
            frame_no=frame_no,
            horse_name=horse_name,
            sex=sex,
            age=age,
            weight=weight,
            jockey=jockey,
            trainer=trainer,
            odds=odds,
            popularity=popularity,
            past_races=past_races,
        )

    def _get_past_data_cells(self, row2: Tag) -> list[str]:
        """行2（父名・調教師・前走人気/馬体重/騎手/斤量）から前走データセルのテキストを返す"""
        cells = row2.find_all("td")
        # colspan="3"(父名) と colspan="1"(調教師) と rowspan="2"(odds_weight) を除外
        result = []
        for td in cells:
            colspan = int(td.get("colspan", 1))
            rowspan = int(td.get("rowspan", 1))
            cls = " ".join(td.get("class", []))
            if colspan > 1 or rowspan > 1 or "odds_weight" in cls:
                continue
            result.append(td.get_text(strip=True))
        return result

    def _parse_past_race(
        self,
        info_div: Tag,
        race_link: Optional[Tag],
        cell_row2: str,
        race: Race,
    ) -> Optional[PastRace]:
        """raceInfoブロック1つ分をPastRaceに変換する"""
        # 着順
        rank_span = info_div.find("span", class_="pastRank")
        finishing_pos = 0
        if rank_span:
            t = rank_span.get_text(strip=True)
            if t.isdigit():
                finishing_pos = int(t)

        text = info_div.get_text(" ", strip=True)

        # 日付: "26.03.24" → "2026/03/24"
        dm = re.search(r"(\d{2})\.(\d{2})\.(\d{2})", text)
        race_date_str = ""
        if dm:
            race_date_str = f"20{dm.group(1)}/{dm.group(2)}/{dm.group(3)}"

        # 競馬場名・方向・距離: "高知　右1400　12番" or "船橋ナ　左1800　7番"
        track_m = re.search(r"([^\s\d]+?)\s+[左右直]?(\d{3,4})\s", text)
        baba_name = track_m.group(1).strip() if track_m else ""
        dist = int(track_m.group(2)) if track_m else 0

        # レース名
        race_name_str = race_link.get_text(strip=True) if race_link else ""

        # 行2セル: "3人　505　岩田望 58.0"
        past_horse_weight = 0
        past_weight = 0.0
        if cell_row2:
            hw_m = re.search(r"\b(\d{3,4})\b", cell_row2)
            if hw_m:
                past_horse_weight = int(hw_m.group(1))
            w_m = re.search(r"(\d{2,3}\.\d)", cell_row2)
            if w_m:
                try:
                    past_weight = float(w_m.group(1))
                except ValueError:
                    pass

        if not race_date_str and finishing_pos == 0:
            return None

        return PastRace(
            race_date=race_date_str,
            baba_name=baba_name,
            race_name=race_name_str,
            distance=dist,
            finishing_pos=finishing_pos,
            jockey="",
            weight=past_weight,
            horse_weight=past_horse_weight,
            horse_weight_diff=0,
        )
