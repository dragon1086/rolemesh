from __future__ import annotations

import os
import stat
import subprocess


def test_quickstart_run_demo_uses_expected_cli_commands(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "python3.log"
    stub = bin_dir / "python3"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$ROLEMESH_QUICKSTART_LOG\"\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ROLEMESH_QUICKSTART_LOG"] = str(log_path)

    subprocess.run(
        ["bash", "examples/quickstart/run_demo.sh"],
        cwd="/Users/rocky/rolemesh",
        env=env,
        check=True,
    )

    commands = log_path.read_text(encoding="utf-8").splitlines()
    assert commands == [
        "-m rolemesh integration list",
        "-m rolemesh route 빌드 실행",
        "-m rolemesh status",
    ]
