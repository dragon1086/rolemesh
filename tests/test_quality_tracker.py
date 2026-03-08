import os
import stat
import subprocess
import threading
import time

import pytest

from rolemesh.core.init_db import get_shared_connection, release_shared_connection
from rolemesh.core.quality_tracker import QualityTracker
from rolemesh.core.registry_client import RegistryClient
from rolemesh.routing.integration import IntegrationManager


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


@pytest.mark.parametrize("score", [-1, 101, float("inf"), float("-inf")])
def test_record_rejects_out_of_range_scores(tmp_path, score):
    tracker = QualityTracker(db_path=str(tmp_path / "quality.db"))
    try:
        with pytest.raises(ValueError, match="between 0 and 100"):
            tracker.record("batch-1", score, "openai")
    finally:
        tracker.close()


def test_get_stats_recent_days_filters_below_threshold_ratio(tmp_path):
    now = time.time()
    tracker = QualityTracker(db_path=str(tmp_path / "quality.db"), threshold=85.0)
    try:
        tracker.record("old-low", 10, "openai", timestamp=now - (10 * 24 * 60 * 60))
        tracker.record("recent-low", 80, "openai", timestamp=now - 60)
        tracker.record("recent-high", 90, "openai", timestamp=now - 30)
        stats = tracker.get_stats(recent_days=7)
        assert stats["count"] == 2
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


def test_shared_connection_reused_across_registry_and_quality_tracker(tmp_path):
    db_path = str(tmp_path / "shared.db")
    tracker = QualityTracker(db_path=db_path)
    client = RegistryClient(db_path=db_path)
    mgr = IntegrationManager(db_path=db_path)
    try:
        assert tracker._conn_ctx() is client._conn_ctx()
        assert tracker._conn_ctx() is mgr._client._conn_ctx()

        tracker.close()

        client.register_agent("bot-a", "Bot A", endpoint="http://localhost:9999")
        rows = client._conn_ctx().execute("SELECT agent_id FROM agents").fetchall()
        assert [row["agent_id"] for row in rows] == ["bot-a"]
    finally:
        client.close()
        mgr.close()


def test_shared_connection_isolated_per_thread(tmp_path):
    db_path = str(tmp_path / "threaded.db")
    main_conn = get_shared_connection(db_path)
    worker_conn_id: list[int] = []

    def _worker() -> None:
        conn = get_shared_connection(db_path)
        try:
            worker_conn_id.append(id(conn))
        finally:
            release_shared_connection(conn, db_path)

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join()

    try:
        assert worker_conn_id
        assert worker_conn_id[0] != id(main_conn)
    finally:
        release_shared_connection(main_conn, db_path)


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
