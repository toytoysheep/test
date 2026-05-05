from dataclasses import dataclass, field
from datetime import date
from typing import Optional


BABA_CODE_MAP: dict[str, str] = {
    "3":  "帯広（ばんえい）",
    "10": "盛岡",
    "14": "水沢",
    "19": "船橋",
    "20": "大井",
    "21": "川崎",
    "22": "金沢",
    "24": "名古屋",
    "27": "園田",
    "28": "姫路",
    "31": "高知",
    "32": "佐賀",
    "36": "門別",
}


@dataclass
class Race:
    race_date: date
    baba_code: str
    race_no: int
    race_name: str = ""
    grade: str = ""          # "Jpn1", "Jpn2", "Jpn3", "G1", "G2", "G3"
    distance: int = 0        # メートル
    track_type: str = ""     # "ダート", "芝", "障害"
    direction: str = ""      # "右", "左", "直線"
    start_time: str = ""     # "20:05" 形式
    racecard_url: str = ""   # dirtgraderace racecard.html URL（race_no解決に使用）
    horses: list = field(default_factory=list)

    @property
    def baba_name(self) -> str:
        return BABA_CODE_MAP.get(self.baba_code, f"不明({self.baba_code})")

    @property
    def race_id(self) -> str:
        return f"{self.race_date.strftime('%Y%m%d')}_{self.baba_code}_{self.race_no}"

    def __str__(self) -> str:
        lines = [
            f"レース名  : {self.race_name} ({self.grade})",
            f"開催日    : {self.race_date.strftime('%Y年%-m月%-d日')}",
            f"競馬場    : {self.baba_name} {self.direction}{self.distance}m",
        ]
        if self.start_time:
            lines.append(f"発走時刻  : {self.start_time}")
        return "\n".join(lines)
