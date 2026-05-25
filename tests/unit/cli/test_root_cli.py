import re

from typer.testing import CliRunner

from adrift.cli.root import app

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _normalized_help(text: str) -> str:
    # CI may emit ANSI-rich help and wrap option labels; normalize to stable text.
    return _ANSI_RE.sub("", text)


def _assert_has_option(help_text: str, option_name: str) -> None:
    normalized = _normalized_help(help_text)
    assert option_name in normalized


def test_root_help_lists_expected_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"], color=False)

    assert result.exit_code == 0
    assert "cleanup" in result.stdout
    assert "download" in result.stdout
    assert "merge" in result.stdout
    assert "schema" in result.stdout
    assert "help" in result.stdout


def test_help_command_prints_top_level_help() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["help"], color=False)

    assert result.exit_code == 0
    assert "Commands" in result.stdout
    assert "cleanup" in result.stdout
    assert "download" in result.stdout
    assert "merge" in result.stdout
    assert "schema" in result.stdout


def test_help_download_shows_download_options() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["help", "download"], color=False)

    assert result.exit_code == 0
    _assert_has_option(result.stdout, "--max-downloads")
    _assert_has_option(result.stdout, "--skip-download")


def test_download_help_shows_download_options() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["download", "--help"], color=False)

    assert result.exit_code == 0
    _assert_has_option(result.stdout, "--max-downloads")
    _assert_has_option(result.stdout, "--skip-download")


def test_help_unknown_command_returns_error() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["help", "unknown-command"], color=False)

    assert result.exit_code != 0
    assert "Unknown command" in result.output
