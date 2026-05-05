from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PastRace:
    """1レース分の過去成績"""
    race_date: str           # "2026/04/01"
    baba_name: str
    race_name: str
    distance: int
    finishing_pos: int       # 着順（0=除外/取消）
    jockey: str
    weight: float            # 斤量
    horse_weight: int        # 馬体重（kg）
    horse_weight_diff: int   # 馬体重増減


@dataclass
class Horse:
    horse_no: int            # 馬番
    frame_no: int            # 枠番
    horse_name: str
    sex: str                 # "牡", "牝", "セ"
    age: int
    weight: float            # 斤量
    jockey: str
    trainer: str
    owner: str = ""
    horse_weight: int = 0
    horse_weight_diff: int = 0
    odds: Optional[float] = None
    popularity: Optional[int] = None
    past_races: list[PastRace] = field(default_factory=list)
    score: float = 0.0            # 予想スコア（predictor が設定）
    deviation_score: float = 0.0  # 偏差値（predictor が設定）
    rank: int = 0                 # 予想順位（predictor が設定）

    @property
    def mark(self) -> str:
        marks = {1: "◎", 2: "○", 3: "▲", 4: "△", 5: "×"}
        return marks.get(self.rank, "　")

    @property
    def last_finish(self) -> Optional[int]:
        """前走着順（データがなければ None）"""
        if self.past_races:
            return self.past_races[0].finishing_pos
        return None
