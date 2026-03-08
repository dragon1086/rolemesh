import os
from pathlib import Path
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_rolemesh(args: list[str], db_path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": "src",
        "ROLEMESH_DB": str(db_path),
    }
    return subprocess.run(
        [sys.executable, "-m", "rolemesh", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )


def test_rolemesh_init_completes_under_15_minutes(tmp_path):
    db_path = tmp_path / "rolemesh.db"

    started_at = time.perf_counter()
    result = _run_rolemesh(["init", "--yes"], db_path)
    elapsed = time.perf_counter() - started_at

    assert result.returncode == 0, result.stderr or result.stdout
    assert elapsed < 900, f"rolemesh init took {elapsed:.2f}s"


def test_rolemesh_cli_entrypoint_works(tmp_path):
    result = _run_rolemesh(["--help"], tmp_path / "rolemesh.db")
    assert result.returncode == 0, result.stderr or result.stdout


def test_rolemesh_init_creates_db(tmp_path):
    db_path = tmp_path / "isolated-rolemesh.db"

    result = _run_rolemesh(["init", "--yes"], db_path)

    assert result.returncode == 0, result.stderr or result.stdout
    assert db_path.exists()
