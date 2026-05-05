"""統計ベース予想ロジック（LightGBM移行を想定した設計）"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from models.race import Race
from models.horse import Horse

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


# ------------------------------------------------------------------ config


def _load_weights(path: Path = CONFIG_PATH) -> dict[str, float]:
    """config.yaml から scoring セクションの重みを読み込む。
    PyYAML 未インストール時は標準ライブラリのみでパースする。"""
    defaults = {
        "weight_last_finish": 20.0,
        "weight_distance":    10.0,
        "weight_jockey":      15.0,
        "weight_handicap":     8.0,
        "weight_same_track":  12.0,
    }
    if not path.exists():
        return defaults

    try:
        import yaml  # type: ignore
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except ModuleNotFoundError:
        data = _parse_yaml_simple(path)
    except Exception:
        return defaults

    scoring = (data or {}).get("scoring", {})
    return {k: float(scoring.get(k, v)) for k, v in defaults.items()}


def _parse_yaml_simple(path: Path) -> dict:
    """PyYAML なしで config.yaml の scoring ブロックを読む簡易パーサー。
    ネストは scoring: 直下のスカラー値のみ対応。"""
    result: dict = {}
    in_scoring = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.rstrip()
            if stripped.startswith("scoring:"):
                in_scoring = True
                continue
            if in_scoring:
                if stripped and not stripped[0].isspace():
                    break  # scoring ブロック終了
                m_kv = __import__("re").match(r"\s+(\w+):\s*([0-9.]+)", stripped)
                if m_kv:
                    result[m_kv.group(1)] = float(m_kv.group(2))
    return {"scoring": result}


# ------------------------------------------------------------------ feature extraction


@dataclass
class HorseFeatures:
    """スコアリングに使う特徴量（LightGBM移行時はそのまま使用可能）"""
    horse_no: int
    last_finish: int          # 前走着順（0=不明）
    distance_diff: int        # 前走からの距離変化（絶対値）
    weight: float             # 斤量
    jockey_total: int         # 騎手の地方交流重賞出走数
    jockey_wins: int          # 騎手の地方交流重賞1着数
    jockey_top3: int          # 騎手の地方交流重賞3着以内数
    same_track_races: int     # 同競馬場での出走数
    same_track_wins: int      # 同競馬場での1着数


def extract_features(horse: Horse, race: Race, jockey_stats: dict) -> HorseFeatures:
    last_finish = horse.last_finish or 0
    distance_diff = 0
    if horse.past_races and race.distance:
        distance_diff = abs(horse.past_races[0].distance - race.distance)

    same_track_races = sum(
        1 for p in horse.past_races if p.baba_name == race.baba_name
    )
    same_track_wins = sum(
        1 for p in horse.past_races
        if p.baba_name == race.baba_name and p.finishing_pos == 1
    )

    return HorseFeatures(
        horse_no=horse.horse_no,
        last_finish=last_finish,
        distance_diff=distance_diff,
        weight=horse.weight,
        jockey_total=jockey_stats.get("total", 0),
        jockey_wins=jockey_stats.get("wins", 0),
        jockey_top3=jockey_stats.get("top3", 0),
        same_track_races=same_track_races,
        same_track_wins=same_track_wins,
    )


# ------------------------------------------------------------------ scoring


class ScoringModel(Protocol):
    def score(self, features: HorseFeatures) -> float: ...


class StatisticalModel:
    """統計ベースのシンプルなスコアリングモデル。重みは config.yaml から読み込む。"""

    def __init__(self, config_path: Path = CONFIG_PATH):
        w = _load_weights(config_path)
        self.w_last_finish  = w["weight_last_finish"]
        self.w_distance     = w["weight_distance"]
        self.w_jockey       = w["weight_jockey"]
        self.w_handicap     = w["weight_handicap"]
        self.w_same_track   = w["weight_same_track"]
        self._max_possible  = (
            self.w_last_finish + self.w_distance + self.w_jockey
            + self.w_handicap + self.w_same_track
        )

    def score(self, features: HorseFeatures) -> float:
        total = 0.0

        # 前走着順（1着=満点、着順が下がるほど減点）
        if features.last_finish > 0:
            finish_score = max(0.0, (10 - features.last_finish) / 9.0)
            total += self.w_last_finish * finish_score

        # 距離変化（前走データがある場合のみ加点）
        if features.last_finish > 0 and features.distance_diff <= 200:
            dist_score = 1.0 - features.distance_diff / 200.0
            total += self.w_distance * dist_score

        # 騎手実績（勝率×0.6 + 3着内率×0.4）
        if features.jockey_total > 0:
            win_rate  = features.jockey_wins  / features.jockey_total
            top3_rate = features.jockey_top3  / features.jockey_total
            jockey_score = win_rate * 0.6 + top3_rate * 0.4
            experience_bonus = min(1.0, features.jockey_total / 20)
            total += self.w_jockey * jockey_score * experience_bonus

        # 斤量（56kg基準、軽いほど有利。データなし=0は除外）
        if features.weight > 0:
            weight_diff  = 56.0 - features.weight
            weight_score = max(0.0, min(1.0, 0.5 + weight_diff / 4.0))
            total += self.w_handicap * weight_score

        # 同競馬場実績（勝率 × 経験補正）
        if features.same_track_races > 0:
            track_win_rate = features.same_track_wins / features.same_track_races
            track_bonus    = min(1.0, features.same_track_races / 3)
            total += self.w_same_track * track_win_rate * track_bonus

        return round(total / self._max_possible * 100, 1)


# ------------------------------------------------------------------ predictor


class Predictor:
    def __init__(self, db=None, model: Optional[ScoringModel] = None):
        self._db = db
        self._model = model or StatisticalModel()

    def predict(self, race: Race) -> Race:
        """race.horses にスコアと順位を付けて返す"""
        scored: list[tuple[float, Horse]] = []

        for horse in race.horses:
            jockey_stats = {}
            if self._db:
                jockey_stats = self._db.jockey_graded_stats(horse.jockey)

            features = extract_features(horse, race, jockey_stats)
            horse.score = self._model.score(features)
            scored.append((horse.score, horse))

        scored.sort(key=lambda x: x[0], reverse=True)
        for rank, (_, horse) in enumerate(scored, start=1):
            horse.rank = rank

        scores = [h.score for h in race.horses]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std = variance ** 0.5

        for horse in race.horses:
            if std == 0:
                horse.deviation_score = 50.0
            else:
                horse.deviation_score = round((horse.score - mean) / std * 10 + 50, 1)

        race.horses.sort(key=lambda h: h.horse_no)
        return race
