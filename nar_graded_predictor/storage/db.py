"""SQLite によるレース・馬データの保存と読み込み"""
import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

from models.race import Race
from models.horse import Horse, PastRace

DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "races.db"


class Database:
    def __init__(self, path: Path = DEFAULT_DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------ schema

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS races (
                race_id     TEXT PRIMARY KEY,
                race_date   TEXT NOT NULL,
                baba_code   TEXT NOT NULL,
                race_no     INTEGER NOT NULL,
                race_name   TEXT,
                grade       TEXT,
                distance    INTEGER,
                track_type  TEXT,
                direction   TEXT,
                start_time  TEXT,
                racecard_url TEXT
            );

            CREATE TABLE IF NOT EXISTS horses (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id         TEXT NOT NULL REFERENCES races(race_id),
                horse_no        INTEGER,
                frame_no        INTEGER,
                horse_name      TEXT,
                sex             TEXT,
                age             INTEGER,
                weight          REAL,
                jockey          TEXT,
                trainer         TEXT,
                horse_weight    INTEGER,
                horse_weight_diff INTEGER,
                odds            REAL,
                popularity      INTEGER,
                past_races_json TEXT,
                score           REAL,
                rank            INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_horses_race_id ON horses(race_id);
        """)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """既存DBに不足カラムを追加するマイグレーション"""
        existing = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(races)").fetchall()
        }
        migrations = [
            ("racecard_url", "ALTER TABLE races ADD COLUMN racecard_url TEXT"),
        ]
        for col, sql in migrations:
            if col not in existing:
                self._conn.execute(sql)

    # ------------------------------------------------------------------ write

    def save_race(self, race: Race) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO races
            (race_id, race_date, baba_code, race_no, race_name,
             grade, distance, track_type, direction, start_time, racecard_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            race.race_id,
            race.race_date.isoformat(),
            race.baba_code,
            race.race_no,
            race.race_name,
            race.grade,
            race.distance,
            race.track_type,
            race.direction,
            race.start_time,
            race.racecard_url,
        ))

        for horse in race.horses:
            self._upsert_horse(race.race_id, horse)

        self._conn.commit()

    def _upsert_horse(self, race_id: str, horse: Horse) -> None:
        past_json = json.dumps(
            [vars(p) for p in horse.past_races], ensure_ascii=False
        )
        self._conn.execute("""
            INSERT OR REPLACE INTO horses
            (race_id, horse_no, frame_no, horse_name, sex, age, weight,
             jockey, trainer, horse_weight, horse_weight_diff,
             odds, popularity, past_races_json, score, rank)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            race_id,
            horse.horse_no,
            horse.frame_no,
            horse.horse_name,
            horse.sex,
            horse.age,
            horse.weight,
            horse.jockey,
            horse.trainer,
            horse.horse_weight,
            horse.horse_weight_diff,
            horse.odds,
            horse.popularity,
            past_json,
            horse.score,
            horse.rank,
        ))

    # ------------------------------------------------------------------ read

    def load_race(self, race_id: str) -> Optional[Race]:
        row = self._conn.execute(
            "SELECT * FROM races WHERE race_id = ?", (race_id,)
        ).fetchone()
        if not row:
            return None

        race = Race(
            race_date=date.fromisoformat(row["race_date"]),
            baba_code=row["baba_code"],
            race_no=row["race_no"],
            race_name=row["race_name"] or "",
            grade=row["grade"] or "",
            distance=row["distance"] or 0,
            track_type=row["track_type"] or "",
            direction=row["direction"] or "",
            start_time=row["start_time"] or "",
            racecard_url=row["racecard_url"] or "",
        )
        race.horses = self._load_horses(race_id)
        return race

    def _load_horses(self, race_id: str) -> list[Horse]:
        rows = self._conn.execute(
            "SELECT * FROM horses WHERE race_id = ? ORDER BY horse_no", (race_id,)
        ).fetchall()

        horses = []
        for row in rows:
            past = []
            if row["past_races_json"]:
                for p in json.loads(row["past_races_json"]):
                    past.append(PastRace(**p))

            h = Horse(
                horse_no=row["horse_no"],
                frame_no=row["frame_no"],
                horse_name=row["horse_name"] or "",
                sex=row["sex"] or "",
                age=row["age"] or 0,
                weight=row["weight"] or 0.0,
                jockey=row["jockey"] or "",
                trainer=row["trainer"] or "",
                horse_weight=row["horse_weight"] or 0,
                horse_weight_diff=row["horse_weight_diff"] or 0,
                odds=row["odds"],
                popularity=row["popularity"],
                past_races=past,
                score=row["score"] or 0.0,
                rank=row["rank"] or 0,
            )
            horses.append(h)
        return horses

    def race_exists(self, race_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM races WHERE race_id = ?", (race_id,)
        ).fetchone()
        return row is not None

    def list_races(self, from_date: Optional[date] = None) -> list[str]:
        """保存済みレースIDの一覧を返す"""
        if from_date:
            rows = self._conn.execute(
                "SELECT race_id FROM races WHERE race_date >= ? ORDER BY race_date",
                (from_date.isoformat(),),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT race_id FROM races ORDER BY race_date"
            ).fetchall()
        return [r["race_id"] for r in rows]

    # ------------------------------------------------------------------ jockey stats

    def jockey_graded_stats(self, jockey: str) -> dict:
        """騎手の地方交流重賞での過去成績集計"""
        rows = self._conn.execute("""
            SELECT h.horse_no, h.rank AS finish_pos
            FROM horses h
            JOIN races r ON h.race_id = r.race_id
            WHERE h.jockey = ?
              AND r.grade != ''
        """, (jockey,)).fetchall()

        total = len(rows)
        wins = sum(1 for r in rows if r["finish_pos"] == 1)
        top3 = sum(1 for r in rows if r["finish_pos"] and r["finish_pos"] <= 3)
        return {"total": total, "wins": wins, "top3": top3}
