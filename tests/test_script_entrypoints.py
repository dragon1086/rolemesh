from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rolemesh_init_uses_cli_installer_module():
    script = (ROOT / "scripts" / "rolemesh-init.sh").read_text(encoding="utf-8")
    assert "-m rolemesh.cli.installer" in script


def test_worker_wrappers_use_workers_package_modules():
    expected = {
        "run_queue_worker.sh": "rolemesh.workers.queue_worker",
        "run_message_worker.sh": "rolemesh.workers.message_worker",
        "run_autoevo.sh": "rolemesh.workers.autoevo_worker",
    }

    for name, module in expected.items():
        script = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert f"-m {module}" in script
