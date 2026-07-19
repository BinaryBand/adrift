"""Tests for the cli layer."""

from __future__ import annotations

from typer.testing import CliRunner

from adrift.cli.main import app

runner = CliRunner()


def test_status_runs() -> None:
    # With a single command, Typer runs it directly (no subcommand name), so
    # invoke with no args. Once more commands exist this shows help -- still
    # exit 0 -- so the smoke test stays valid as the cli layer grows.
    result = runner.invoke(app, [])
    assert result.exit_code == 0
