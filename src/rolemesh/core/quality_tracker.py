from __future__ import annotations

import logging
import os
import sqlite3
import time
from math import isfinite

from .init_db import DEFAULT_DB_PATH, get_shared_connection, release_shared_connection

logger = logging.getLogger(__name__)


class QualityTracker:
    def __init__(self, db_path: str = DEFAULT_DB_PATH, threshold: float = 85.0):
        self.db_path = os.path.expanduser(db_path)
        self.threshold = float(threshold)
        self._conn = get_shared_connection(self.db_path)

    def close(self) -> None:
        release_shared_connection(self._conn, self.db_path)
        self._conn = None

    def _conn_ctx(self) -> sqlite3.Connection:
        try:
            if self._conn is None:
                raise sqlite3.ProgrammingError("connection is closed")
            self._conn.execute("SELECT 1")
        except sqlite3.Error:
            logger.debug("Reopening shared quality DB connection for %s", self.db_path)
            self._conn = get_shared_connection(self.db_path)
        return self._conn

    def record(
        self,
        batch_id: str,
        score: float,
        provider: str,
        timestamp: float | None = None,
    ) -> None:
        score_value = float(score)
        if not isfinite(score_value) or not 0.0 <= score_value <= 100.0:
            raise ValueError("score must be a finite value between 0 and 100")
        conn = self._conn_ctx()
        conn.execute(
            """
            INSERT INTO quality_scores (batch_id, score, provider, ts)
            VALUES (?, ?, ?, ?)
            """,
            (
                batch_id,
                score_value,
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
