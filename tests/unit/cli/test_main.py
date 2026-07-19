"""Tests for the cli layer."""

from __future__ import annotations

from typer.testing import CliRunner

from adrift.cli.main import app

runner = CliRunner()


def test_status_runs() -> None:
    # `no_args_is_help=True` on a multi-command app: invoking with no args
    # prints help. Click >=8.2 treats this as a usage error (exit code 2)
    # rather than a clean exit, so assert on the help text, not the code.
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Usage:" in result.output
