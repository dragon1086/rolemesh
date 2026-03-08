from __future__ import annotations

import os
import sqlite3
import time

from .init_db import DEFAULT_DB_PATH, init_db


class QualityTracker:
    def __init__(self, db_path: str = DEFAULT_DB_PATH, threshold: float = 85.0):
        self.db_path = os.path.expanduser(db_path)
        self.threshold = float(threshold)
        self._conn = init_db(self.db_path)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def _conn_ctx(self) -> sqlite3.Connection:
        try:
            self._conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            self._conn = init_db(self.db_path)
        return self._conn

    def record(
        self,
        batch_id: str,
        score: float,
        provider: str,
        timestamp: float | None = None,
    ) -> None:
        conn = self._conn_ctx()
        conn.execute(
            """
            INSERT INTO quality_scores (batch_id, score, provider, ts)
            VALUES (?, ?, ?, ?)
            """,
            (
                batch_id,
                float(score),
                provider or "unknown",
                float(time.time() if timestamp is None else timestamp),
            ),
        )
        conn.commit()

    def get_weekly_average(self) -> float | None:
        conn = self._conn_ctx()
        cutoff = time.time() - (7 * 24 * 60 * 60)
        row = conn.execute(
            "SELECT AVG(score) AS average FROM quality_scores WHERE ts >= ?",
            (cutoff,),
        ).fetchone()
        value = row["average"] if row is not None else None
        return None if value is None else float(value)

    def get_stats(self, recent_days: int | None = None) -> dict[str, float | int | None]:
        conn = self._conn_ctx()
        params: tuple[float, ...] = ()
        where = ""
        if recent_days is not None:
            cutoff = time.time() - (recent_days * 24 * 60 * 60)
            where = "WHERE ts >= ?"
            params = (cutoff,)

        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS count,
                AVG(score) AS average,
                MIN(score) AS min_score,
                MAX(score) AS max_score,
                AVG(CASE WHEN score < ? THEN 1.0 ELSE 0.0 END) AS below_ratio
            FROM quality_scores
            {where}
            """,
            (self.threshold, *params),
        ).fetchone()

        count = int(row["count"] or 0)
        return {
            "count": count,
            "average": None if row["average"] is None else float(row["average"]),
            "min": None if row["min_score"] is None else float(row["min_score"]),
            "max": None if row["max_score"] is None else float(row["max_score"]),
            "below_threshold_ratio": None if count == 0 else float(row["below_ratio"]),
        }
