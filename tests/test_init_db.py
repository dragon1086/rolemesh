from __future__ import annotations

from rolemesh.core.init_db import get_shared_connection, release_shared_connection


def test_shared_connection_reopens_after_release(tmp_path):
    db_path = str(tmp_path / "registry.db")

    first = get_shared_connection(db_path)
    release_shared_connection(first, db_path)

    reopened = get_shared_connection(db_path)
    try:
        row = reopened.execute("SELECT 1 AS value").fetchone()
    finally:
        release_shared_connection(reopened, db_path)

    assert row["value"] == 1
