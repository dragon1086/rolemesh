from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {
    "run_queue_worker.sh": "rolemesh.workers.queue_worker",
    "run_message_worker.sh": "rolemesh.workers.message_worker",
    "run_autoevo.sh": "rolemesh.workers.autoevo_worker",
    "rolemesh-init.sh": "rolemesh.cli.installer",
}


def test_scripts_exist_and_have_valid_bash_syntax():
    for name in SCRIPTS:
        script_path = ROOT / "scripts" / name
        assert script_path.is_file(), f"missing script: {script_path}"
        result = subprocess.run(
            ["bash", "-n", str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_scripts_use_expected_modules():
    for name, module in SCRIPTS.items():
        script = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert f"-m {module}" in script
