from __future__ import annotations

import pytest

from rolemesh.cli import __main__ as cli_main


def test_main_reports_suggest_parse_errors(monkeypatch, capsys):
    monkeypatch.setattr(cli_main.sys, "argv", ["rolemesh", "suggest", "--unknown"])

    with pytest.raises(SystemExit) as exc:
        cli_main.main()

    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "usage: rolemesh suggest" in captured.out


def test_main_reports_runtime_errors(monkeypatch, capsys):
    def boom():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(cli_main, "_cmd_agents", boom)
    monkeypatch.setattr(cli_main.sys, "argv", ["rolemesh", "agents"])

    with pytest.raises(SystemExit) as exc:
        cli_main.main()

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "RuntimeError: db unavailable" in captured.out


def test_integration_missing_subcommand_exits_with_usage():
    with pytest.raises(cli_main.CLIUsageError, match="integration <add\\|list\\|remove>"):
        cli_main._cmd_integration([])


class _DummyIntegrationManager:
    def __init__(self):
        self.received = None

    def add(self, **kwargs):
        self.received = kwargs
        return {
            "name": kwargs["name"],
            "role": kwargs["role"],
            "endpoint": kwargs["endpoint"],
            "capabilities": kwargs["capabilities"],
            "script_path": "/tmp/nanoclaw-delegate.sh",
        }


def test_integration_add_defaults_endpoint_and_prints_human_message(capsys):
    mgr = _DummyIntegrationManager()

    cli_main._integration_add(
        mgr,
        [
            "--name", "nanoclaw",
            "--role", "builder",
            "--cmd", "nanoclaw --stdio",
            "--provider", "nanoclaw",
            "--capabilities", "build,review",
        ],
    )

    assert mgr.received is not None
    assert mgr.received["endpoint"] == "local://nanoclaw"
    captured = capsys.readouterr()
    assert "추가 완료: 'nanoclaw' AI를 RoleMesh에 등록했습니다." in captured.out
    assert "연결 주소: local://nanoclaw  (입력하지 않아 자동으로 채움)" in captured.out
    assert "실행 스크립트: /tmp/nanoclaw-delegate.sh" in captured.out
    assert "확인 명령: rolemesh integration list" in captured.out
