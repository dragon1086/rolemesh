#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
DB_PATH="${ROLEMESH_DB_PATH:-$HOME/ai-comms/registry.db}"

python3 - "$DB_PATH" "$MODE" <<'PY'
import sqlite3
import sys
import time

db_path = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else ""
recent_days = 7 if mode == "--week" else None
threshold = 85.0

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS quality_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        score REAL NOT NULL,
        provider TEXT NOT NULL,
        ts REAL NOT NULL
    )
    """
)
conn.commit()

where = ""
params = []
label = "전체"
if recent_days is not None:
    where = "WHERE ts >= ?"
    params.append(time.time() - recent_days * 24 * 60 * 60)
    label = "최근 7일"

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
    [threshold, *params],
).fetchone()

count = int(row["count"] or 0)
average = None if row["average"] is None else float(row["average"])
min_score = None if row["min_score"] is None else float(row["min_score"])
max_score = None if row["max_score"] is None else float(row["max_score"])
below_ratio = None if count == 0 else float(row["below_ratio"])
status = "✅" if average is not None and average >= threshold else "❌"

def fmt(value):
    return "-" if value is None else f"{value:.2f}"

print(f"quality-report ({label}) {status}")
print(f"count: {count}")
print(f"average: {fmt(average)}")
print(f"min: {fmt(min_score)}")
print(f"max: {fmt(max_score)}")
print(f"below_threshold_ratio: {fmt(None if below_ratio is None else below_ratio * 100)}%")
print(f"target_weekly_average: >= {threshold:.0f}")
PY
