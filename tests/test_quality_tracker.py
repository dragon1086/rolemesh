import os
import stat
import subprocess
import time

from rolemesh.core.quality_tracker import QualityTracker


def test_quality_tracker_instance_creation(tmp_path):
    tracker = QualityTracker(db_path=str(tmp_path / "quality.db"))
    try:
        assert isinstance(tracker, QualityTracker)
    finally:
        tracker.close()


def test_record_single_score_persists(tmp_path):
    db_path = str(tmp_path / "quality.db")
    tracker = QualityTracker(db_path=db_path)
    try:
        tracker.record("batch-1", 90, "openai", timestamp=1700000000)
        row = tracker._conn_ctx().execute(
            "SELECT batch_id, score, provider, ts FROM quality_scores"
        ).fetchone()
        assert row["batch_id"] == "batch-1"
        assert row["score"] == 90
        assert row["provider"] == "openai"
        assert row["ts"] == 1700000000
    finally:
        tracker.close()


def test_record_multiple_scores_persist(tmp_path):
    tracker = QualityTracker(db_path=str(tmp_path / "quality.db"))
    try:
        tracker.record("batch-1", 90, "openai")
        tracker.record("batch-2", 80, "anthropic")
        row = tracker._conn_ctx().execute(
            "SELECT COUNT(*) AS count FROM quality_scores"
        ).fetchone()
        assert row["count"] == 2
    finally:
        tracker.close()


def test_get_weekly_average_returns_expected_value(tmp_path):
    now = time.time()
    tracker = QualityTracker(db_path=str(tmp_path / "quality.db"))
    try:
        tracker.record("batch-1", 90, "openai", timestamp=now - 60)
        tracker.record("batch-2", 80, "anthropic", timestamp=now - 120)
        assert tracker.get_weekly_average() == 85.0
    finally:
        tracker.close()


def test_get_stats_returns_expected_shape(tmp_path):
    tracker = QualityTracker(db_path=str(tmp_path / "quality.db"))
    try:
        tracker.record("batch-1", 90, "openai")
        tracker.record("batch-2", 70, "anthropic")
        stats = tracker.get_stats()
        assert set(stats) == {"count", "average", "min", "max", "below_threshold_ratio"}
        assert stats["count"] == 2
        assert stats["average"] == 80.0
        assert stats["min"] == 70.0
        assert stats["max"] == 90.0
        assert stats["below_threshold_ratio"] == 0.5
    finally:
        tracker.close()


def test_weekly_average_excludes_scores_older_than_seven_days(tmp_path):
    now = time.time()
    tracker = QualityTracker(db_path=str(tmp_path / "quality.db"))
    try:
        tracker.record("old-batch", 10, "openai", timestamp=now - (8 * 24 * 60 * 60))
        tracker.record("new-batch", 90, "openai", timestamp=now - 60)
        assert tracker.get_weekly_average() == 90.0
    finally:
        tracker.close()


def test_get_weekly_average_returns_none_for_empty_db(tmp_path):
    tracker = QualityTracker(db_path=str(tmp_path / "quality.db"))
    try:
        assert tracker.get_weekly_average() is None
    finally:
        tracker.close()


def test_quality_report_script_exists_and_is_executable():
    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "quality-report.sh")
    st = os.stat(script_path)
    assert os.path.exists(script_path)
    assert bool(st.st_mode & stat.S_IXUSR)


def test_quality_report_script_contains_quality_report():
    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "quality-report.sh")
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "quality-report" in content


def test_quality_report_script_outputs_weekly_stats(tmp_path):
    db_path = str(tmp_path / "quality.db")
    tracker = QualityTracker(db_path=db_path)
    try:
        tracker.record("batch-1", 90, "openai", timestamp=time.time() - 60)
    finally:
        tracker.close()

    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "quality-report.sh")
    result = subprocess.run(
        [script_path, "--week"],
        capture_output=True,
        text=True,
        env={**os.environ, "ROLEMESH_DB_PATH": db_path},
        check=True,
    )

    assert "quality-report" in result.stdout
    assert "최근 7일" in result.stdout
    assert "✅" in result.stdout
