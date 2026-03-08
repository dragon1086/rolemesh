from __future__ import annotations

import os
import plistlib
import sqlite3
import subprocess
import sys
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
STATUS_SCRIPT = SCRIPTS_DIR / "status.sh"
PLIST_PATH = SCRIPTS_DIR / "com.rolemesh.worker.plist"


def test_status_script_handles_missing_dead_letter_table(tmp_path):
    home = tmp_path / "home"
    db_dir = home / "ai-comms"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "registry.db"

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE task_queue (id INTEGER PRIMARY KEY, status TEXT NOT NULL)")
    conn.executemany(
        "INSERT INTO task_queue(status) VALUES (?)",
        [("pending",), ("done",), ("done",)],
    )
    conn.commit()
    conn.close()

    env = {
        **os.environ,
        "HOME": str(home),
        "PYTHONPATH": str(REPO_ROOT / "src"),
    }
    result = subprocess.run(
        ["bash", str(STATUS_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "dlq_count: N/A (dead_letter 테이블 없음)" in result.stdout
    assert "pending" in result.stdout
    assert "done" in result.stdout


def test_launchd_plist_paths_and_environment_are_consistent():
    with PLIST_PATH.open("rb") as f:
        plist = plistlib.load(f)

    program_args = plist["ProgramArguments"]
    env = plist["EnvironmentVariables"]
    working_dir = Path(plist["WorkingDirectory"])

    assert program_args[0] == "/bin/bash"
    assert Path(program_args[1]).is_file()
    assert working_dir.is_dir()
    assert env["ROLEMESH_PROJECT_ROOT"] == str(working_dir)
    assert Path(env["PYTHONPATH"]).is_dir()
    assert Path(env["PYTHONPATH"]) == working_dir / "src"
    assert Path(env["ROLEMESH_DB_PATH"]).is_file()
    assert env["HOME"] == str(working_dir.parent)


def test_delegate_scripts_export_repo_src_on_pythonpath():
    repo_src = 'export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"'
    for name in ("cokac-delegate.sh", "codex-delegate.sh"):
        content = (SCRIPTS_DIR / name).read_text(encoding="utf-8")
        assert repo_src in content


def test_delegate_scripts_have_valid_bash_syntax():
    for name in ("cokac-delegate.sh", "codex-delegate.sh"):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPTS_DIR / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"


def test_conftest_keeps_only_required_legacy_aliases():
    sys.modules.pop("contracts", None)
    sys.modules.pop("registry_client", None)
    sys.modules.pop("amp_caller", None)

    import conftest
    importlib.reload(conftest)

    assert "contracts" in sys.modules
    assert "registry_client" in sys.modules
    assert "amp_caller" in sys.modules
    assert "queue_worker" not in sys.modules
    assert "message_worker" not in sys.modules
    assert "autoevo_worker" not in sys.modules
