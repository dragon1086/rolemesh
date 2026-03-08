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
