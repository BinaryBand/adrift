from typer.testing import CliRunner

from adrift.cli.root import app


def test_root_help_lists_expected_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "download" in result.stdout
    assert "merge" in result.stdout
    assert "help" in result.stdout


def test_help_command_prints_top_level_help() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["help"])

    assert result.exit_code == 0
    assert "Commands" in result.stdout
    assert "download" in result.stdout
    assert "merge" in result.stdout


def test_help_download_shows_download_options() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["help", "download"])

    assert result.exit_code == 0
    assert "--max-downloads" in result.stdout
    assert "--skip-download" in result.stdout


def test_download_help_shows_download_options() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["download", "--help"])

    assert result.exit_code == 0
    assert "--max-downloads" in result.stdout
    assert "--skip-download" in result.stdout


def test_help_unknown_command_returns_error() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["help", "unknown-command"])

    assert result.exit_code != 0
    assert "Unknown command" in result.output
